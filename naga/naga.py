#! /usr/bin/env python
""" naga.py 
This is the file that users should run when calling naga from the command
line.
"""

import optparse
import subprocess
import time
INFO_DEFAULT = 'load'
INFO_CHOICES = {
 'load': ['/bin/cat', '/proc/loadavg', '&&', '/bin/cat', '/proc/cpuinfo', '|',
     '/bin/grep', "'model name'", '|', 'wc', '-l'],
 'memory': ['/usr/bin/free', '-m'],
 'cpu': ['/bin/cat', '/proc/stat', '&&', '/bin/sleep', '1', '&&', '/bin/cat',
     '/proc/stat'],
 'disk':['/usr/bin/vmstat', '10', '2'],
#'network': '',
 }

INFO_LEVELS = {
 'load'     : [1.0, 2.0],
 'memory'   : [0.9, 0.95],
 'cpu'      : [0.8, 0.9],
#'network': '',
 'disk'     : [10,30], # Megabytes/s
        }

INFO_UNITS  = {
 'load'     : '',
 'memory'   : '%',
 'cpu'      : '%',
 'disk'     : 'MB/s',
 'network'  : 'MB/s',
}

def timecheck(start_time, timeout, after, proc=None,):
    """ Check if timeout has expired, exit with unknown status if it has."""
    if time.time()-start_time > timeout:
        if proc is not None:
            proc.terminate()
        print 'Unknown: timeout after %s (%ss)' % (after, timeout)
        exit(3)

def parse_opts():
    """ Parse the command line options given to naga."""
    desc = """
    A python plugin for the Nagios monitoring system that connects to remote
    hosts via ssh.  """

    parser = optparse.OptionParser(description=desc)

    # optparse automatically sets up --help for us
    parser.add_option('-t', '--timeout', default='30',
        help='Set timeout (in seconds)')
    parser.add_option('-w', '--warning',
        help='Warning threshold (percentage)')
    parser.add_option('-c', '--critical',
        help='Critical threshold (percentage)')
    parser.add_option('-H', '--hostname', default='localhost',
        help='The hostname or ip of the system to connect to.')
    parser.add_option('-v', '--verbose', action='store_true',
        help='Enable verbose output.')

    parser.add_option('-b', '--binary', default='/usr/bin/ssh',
        help='Path to ssh binary on host.')
    parser.add_option('-l', '--logname',
        help='The login/username used to connect to the remote host. \
                (defaults to current user)')
    parser.add_option('-a', '--authentication',
        help='Authentication password for user at remote host')
    parser.add_option('-p', '--port',
        help='SSH port to use at remote host')
    parser.add_option('-k', '--key',
        help='SSH private key file to use.')
    parser.add_option('-i', '--information', default=INFO_DEFAULT,
            choices=INFO_CHOICES.keys(),
        help='Which type of information to return.')

    return parser.parse_args()

def connect(hostname, info, timeout, binary, start_time=None, **kwargs):
    """ Connect to remote machine via ssh and run relevant command."""
    if start_time == None:
        start_time = time.time()
    cmd1 = [binary]
    if 'logname' in kwargs:
        user = kwargs['logname']
    else:
        import getpass
        user = getpass.getuser()
    
    if 'key' in kwargs:
        cmd1 += ['-i', kwargs['key']]
    if 'port' in kwargs:
        hostname += str(kwargs['port'])
    cmd1.append('%s@%s' % (user, hostname))
    cmd = cmd1 + ['"'] + INFO_CHOICES[info] + ['"']
    if 'verbose' in kwargs:
        print 'about to Popen %s' % ' '.join(cmd)
    proc = subprocess.Popen(' '.join(cmd), shell=True, stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE)
    while proc.poll() is None:
        timecheck(start_time, timeout, 'waiting for Popen', proc)
        time.sleep(float(timeout)/10)
    ret = proc.returncode
    out = proc.stdout.read()
    err = proc.stderr.read()
    return ret, out, err

def memory(ret, out, err, start=None, **kwargs):
    """Get information about memory usage."""
    if ret:
        print 'Unknown: free returned: %s | %s' % (out, err)
        exit(3)
    lines = out.splitlines()
    line1 = lines[1].split()
    line2 = lines[2].split()
    detail = [
            ('total' , int(line1[1])),
            ('used'  , int(line2[2])),
            ('free'  , int(line2[3])),
            ('shared', int(line1[4])),
            ('buff'  , int(line1[5])),
            ('cache' , int(line1[6])),
        ]
    level = float(detail[1][1]) / detail[0][1]
    return level, detail

def load(ret, out, err, start=None, **kwargs):
    """Get load information."""
    if ret:
        print 'Unknown: loadavg returned: %s | %s' % (out, err)
        exit(3)
    lines = out.splitlines()
    split = lines[0].split()
    cores = int(lines[1])
    desc = [
           ('5min',  split[0]),
           ('10min', split[1]),
           ('15min', split[2]),
           ('running', split[3].split('/')[0]),
           ('procs', split[3].split('/')[1]),
           ('last', split[4]),
           ('cores', cores),
            ]
    return float(split[0])/cores, desc

def cpu(ret, out, err, start=None, **kwargs):
    """Get cpu usage."""
    lines = out.splitlines()
    length= len(lines)
    if not length % 2 == 0:
        print 'Unknown: successive calls of /proc/stat were too different'
        exit(3)
    # columns
    # user, nice, system, idle, iowait, irq, softirq
    state = [lines[0].split()[1:], lines[length/2].split()[1:]]

    diff = [sum((int(b),-int(a))) for a, b in zip(*state)]
    total   = sum(diff)
    detail = [
            ('user'    , diff[0]),
            ('nice'    , diff[1]),
            ('system'  , diff[2]),
            ('idle'    , diff[3]),
            ('iowait'  , diff[4]),
            ('irq'     , diff[5]),
            ('softirq' , diff[6]),
        ]
    level = float(total - detail[3][1]) / total
    return level, detail

def disk(ret, out, err, start=None, **kwargs):
    """ Get disk io."""
    mega = 1024*1024
    if 'block' in kwargs:
        block = kwargs['block']
    else:
        block = 4096
    lines = out.splitlines()
    mb_in  = int(lines[-1].split()[8])*block/mega
    mb_out = int(lines[-1].split()[8])*block/mega
    desc = 'mb_in=%s;mb_out=%s' % (mb_in, mb_out)
    return mb_in+mb_out, desc

def filesystem():
    """ Get filesystem usage."""
    raise NotImplementedError

def network():
    """ Get network usage."""
    raise NotImplementedError

def finish(info, level, detail, warn, crit):
    """ Exit with correct status and message."""
    unit = INFO_UNITS[info]
    if unit == '%':
        converted = level*100
    else:
        converted = level
    if warn == None:
        warn = INFO_LEVELS[info][0]
    if crit == None:
        crit = INFO_LEVELS[info][1]
    if type(detail) == list:
        detail = ';'.join(['='.join((k, str(v))) for k,v in detail])
    if warn >= crit:
        print 'Warning: warn (%s) > crit (%s) for %s | %s' % (warn, crit,
                info, detail)
        exit(1)
    if level < warn and level < crit:
        print 'OK: %s usage is %.2g%s | %s' % (info, converted, unit, detail)
        exit(0)
    if level > warn and level < crit:
        print 'Warning: %s usage is high %.2g%s | %s' % (info, converted, unit, detail)
        exit(1)
    if level > crit:
        print 'Critical: %s usage is critical %.2g%s | %s' % (info, converted, unit, detail)
        exit(2)
    else:
        print 'Unknown: no conditions were met'+detail
        exit(3)

def main():
    """ Called when running naga from command line."""
    start = time.time()

    required = ['information', 'hostname', 'binary', 'timeout', 'warning',
            'critical']
    opts = parse_opts()
    info = opts[0].information
    host = opts[0].hostname
    sshb = opts[0].binary
    tout = float(opts[0].timeout)
    try:
        warn = float(opts[0].warning)
    except TypeError:
        warn = None
    try:
        crit = float(opts[0].critical)
    except TypeError:
        crit = None
    kwargs = {}
    for key, val in opts[0].__dict__.items():
        if key not in required and val is not None:
            kwargs[key] = val

    ret, out, err = connect(host, info, tout, sshb, start, **kwargs)
    if not ret == 0:
        print 'Unknown: ssh command returncode %s | out=%s;err=%s ' % (ret, out,
                err)
        exit(3)
    timecheck(start, tout, 'setup')
    if info in globals().keys():
        level, detail = globals()[info](ret, out, err, 
                start=start, timeout=tout)
        timecheck(start, tout, 'after running connect()')
        finish(info, level, detail, warn, crit)
    else:
        print 'Unknown: Could not find processing method for %s' % info
        exit(3)
    
if __name__ == "__main__":
    main()
