#!/usr/local/bin/python3

"""
    Copyright (c) 2022 Ad Schellevis <ad@opnsense.org>
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice,
     this list of conditions and the following disclaimer.

    2. Redistributions in binary form must reproduce the above copyright
     notice, this list of conditions and the following disclaimer in the
     documentation and/or other materials provided with the distribution.

    THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
    INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
    AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
    AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
    OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
    SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
    INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
    CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
    ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
    POSSIBILITY OF SUCH DAMAGE.

    --------------------------------------------------------------------------------------
    handle swanctl.conf updown event
"""
import os
import json
import subprocess
import argparse
import tempfile
import syslog
from configparser import ConfigParser
from lib import list_spds

spd_filename = '/usr/local/etc/swanctl/reqid_events.conf'

spd_add_cmd = 'spdadd -%(ipproto)s %(source)s %(destination)s any ' \
    '-P out ipsec %(protocol)s/tunnel/%(local)s-%(remote)s/unique:%(reqid)s;'

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reqid', default=os.environ.get('PLUTO_REQID'))
    parser.add_argument('--local', default=os.environ.get('PLUTO_ME'))
    parser.add_argument('--remote', default=os.environ.get('PLUTO_PEER'))
    parser.add_argument('--action', default=os.environ.get('PLUTO_VERB'))
    cmd_args = parser.parse_args()
    # init spd's on up-host[-v6], up-client[-v6]
    if cmd_args.action and cmd_args.action.startswith('up'):
        syslog.openlog('charon', logoption=syslog.LOG_DAEMON, facility=syslog.LOG_LOCAL4)
        syslog.syslog(syslog.LOG_NOTICE, '[UPDOWN] received %s event for reqid %s' % (cmd_args.action, cmd_args.reqid))
        if os.path.exists(spd_filename):
            cnf = ConfigParser()
            cnf.read(spd_filename)
            conf_section = 'spd_%s' % cmd_args.reqid
            if cnf.has_section(conf_section):
                spds = {}
                for opt in cnf.options(conf_section):
                    if opt.count('_') == 1:
                        tmp = opt.split('_')
                        seqid = tmp[1]
                        if seqid not in spds:
                            spds[seqid] = {
                                'reqid': cmd_args.reqid,
                                'local' : cmd_args.local,
                                'remote' : cmd_args.remote,
                                'destination': os.environ.get('PLUTO_PEER_CLIENT')
                            }
                        if cnf.get(conf_section, opt).strip() != '':
                            spds[seqid][tmp[0]] = cnf.get(conf_section, opt).strip()
                # (re)aaply manual policies if specified
                cur_spds = list_spds(req_id=cmd_args.reqid, automatic=False)
                set_key = []
                for spd in cur_spds:
                    set_key.append('spddelete -n %(src)s %(dst)s any -P %(direction)s;' % spd)
                for spd in spds.values():
                    if None in spd.values():
                        # incomplete, skip
                        continue
                    spd['ipproto'] = '4' if spd.get('source', '').find(':') == -1 else '6'
                    syslog.syslog(
                        syslog.LOG_NOTICE,
                        '[UPDOWN] add manual policy : %s' % (spd_add_cmd % spd)[7:]
                    )
                    set_key.append(spd_add_cmd % spd)
                if len(set_key) > 0:
                    f = tempfile.NamedTemporaryFile(mode='wt', delete=False)
                    f.write('\n'.join(set_key))
                    f.close()
                    subprocess.run(['/sbin/setkey', '-f', f.name], capture_output=True, text=True)
                    os.unlink(f.name)
