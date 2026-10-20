"""Host regression tests. Requires Python, lupa (Lua 5.1) and a POSIX sh.

Run: python scripts/tests/test-mtk-security.py --sh /path/to/sh --tmp /path/to/tmp
Router operations are stubbed; filesystem fixtures stay under --tmp.
"""
import argparse
from pathlib import Path
import subprocess

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
MTK = ROOT / 'package/mtk/applications'


def read(path):
    return path.read_text(encoding='utf-8')


def new_lua():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        calls, logs, removed = {}, {}, {}
        nixio = {
            fork = function() return 0 end,
            exec = function(...) table.insert(calls, {...}); error('EXEC_STUB') end,
            waitpid = function(pid) return pid, 'exited', 0 end,
            syslog = function(_, msg) table.insert(logs, msg) end
        }
        package.loaded['nixio'] = nixio
        package.loaded['nixio.fs'] = {
            unlink = function(path) table.insert(removed, path) end,
            copy = function(src, dst) table.insert(calls, {'copy', src, dst}); return true end
        }
        package.loaded['l1dat_parser'] = {
            load_l1_profile = function() return {devname_ridx={radio0={
                profile_path='/etc/wireless/test.dat'
            }}} end
        }
        package.loaded['cjson'] = {decode = function() return fixture end}
        package.loaded['datconf'] = {}
        os.execute = function() error('Unexpected shell execution') end
        os.exit = function() error('Unexpected exit') end
        arg = {}
    ''')
    for name in ('inspect', 'mtwifi_utils', 'mtwifi_defs'):
        source = read(MTK / f'mtwifi-cfg/files/mtwifi-cfg/{name}.lua')
        value = lua.execute(source.split('\n', 1)[1] if source.startswith('#!') else source)
        lua.globals().package.loaded[name] = value
    return lua


def test_wireless():
    lua = new_lua()
    lua.execute(read(MTK / 'mtwifi-cfg/files/mtwifi-cfg/mtwifi_cfg').split('\n', 1)[1])
    lua.execute('''
        for _, value in ipairs({'0; printf INJECTED', '$(printf INJECTED)',
            '`printf INJECTED`', '-101', '1', '0.5', '', false, {}}) do
            assert(__exec_iwpriv_cmd('ra0', 'KickStaRssiLow', value) == false)
        end
        assert(__exec_iwpriv_cmd('ra0;id', 'KickStaRssiLow', 0) == false)
        assert(__exec_iwpriv_cmd('-ra0', 'KickStaRssiLow', 0) == false)
        assert(__exec_iwpriv_cmd('-ra0', 'UnknownKey', 0) == false)
        assert(#calls == 0)
        for _, test in ipairs({{'KickStaRssiLow', '-100'},
            {'AssocReqRssiThres', 0}, {'ApCliEnable', 1}, {'ApCliAutoConnect', 3}}) do
            local ok, err = pcall(__exec_iwpriv_cmd, 'ra0', test[1], test[2])
            assert(not ok and err:find('EXEC_STUB'))
            local call = calls[#calls]
            assert(call[1] == '/usr/sbin/iwpriv' and call[2] == 'ra0')
            assert(call[3] == 'set' and call[4] == test[1]..'='..test[2])
        end
        nixio.fork = function() return 10 end
        assert(__exec_iwpriv_cmd('ra0', 'KickStaRssiLow', 0))
        nixio.waitpid = function() return 10, 'exited', 1 end
        assert(not __exec_iwpriv_cmd('ra0', 'KickStaRssiLow', 0))
        nixio.fork = function() return nil end
        assert(not __exec_iwpriv_cmd('ra0', 'KickStaRssiLow', 0))
        -- Run the actual setup path with AP and STA credentials and a changed old key.
        fixture = {device='radio0', config={htmode='HE80', band='5g',
            country='CN', channel=36, txpower=100}, interfaces={
            ['00']={mtwifi_ifname='ra0', config={mode='ap', ssid='test',
                encryption='psk2', key='AP_SECRET'}},
            ['01']={mtwifi_ifname='apcli0', config={mode='sta', ssid='uplink',
                encryption='psk2', key='STA_SECRET'}}}}
        load_profile = function() return {WPAPSK1='OLD_SECRET'} end
        save_profile = function(cfg) saved = cfg end
        mtwifi_down = function() end
        mtwifi_up = function() end
        mtwifi_reinstall = function() end
        mtwifi_cfg_iwpriv_hook = function() end
        package.loaded.mtwifi_utils.exists = function() return true end
        io.open = function() error('Unexpected file logging') end
        mtwifi_cfg_setup('fixture')
        assert(saved.WPAPSK1 == 'AP_SECRET' and saved.ApCliWPAPSK == 'STA_SECRET')
        assert(removed[1] == '/tmp/mtwifi.log')
        for _, message in ipairs(logs) do assert(not message:find('SECRET')) end
    ''')
    print('PASS: wireless rejects injection, preserves argv and never logs AP/STA/old keys')


def test_legacy():
    lua = new_lua()
    lua.execute('''
        package.loaded['ioctl_helper'] = {}
        package.loaded['luci.http'] = {
            status=function(code) last_status=code end, redirect=function() end
        }
        package.loaded['luci.i18n'] = {}
        package.loaded['luci.sys'] = {}
        package.loaded['luci.jsonc'] = {}
        package.loaded.mtkwifi = {
            search_dev_and_profile=function() return {radio0='/etc/wireless/test.dat'} end,
            __run_in_child_env=function(fn, ...) fn(...) end,
            get_referer_url=function() return '/' end
        }
        luci = {http=package.loaded['luci.http'], dispatcher={build_url=function() return '/' end}}
    ''')
    lua.execute(read(MTK / 'luci-app-mtk/luasrc/controller/mtkwifi.lua'))
    lua.execute('''
        local controller = package.loaded['luci.controller.mtkwifi']
        for _, name in ipairs({'radio0;id', 'unknown', '../radio0', '', {}}) do
            controller.reset_wifi(name)
            assert(last_status == 400)
            controller.reset_to_defaults(name)
            assert(last_status == 400)
        end
        assert(#calls == 0)
        controller.reset_wifi('radio0')
        assert(calls[1][1] == 'copy' and calls[1][2] == '/rom/etc/wireless/test.dat')
        assert(calls[1][3] == '/etc/wireless/test.dat')
        for _, name in ipairs({'radio0', false}) do
            local ok, err = pcall(controller.reset_to_defaults, name or nil)
            assert(not ok and err:find('EXEC_STUB'))
            local call = calls[#calls]
            assert(call[1] == '/sbin/wifi' and call[2] == 'reset')
            assert(call[3] == (name or nil))
        end
    ''')
    print('PASS: legacy reset rejects unknown/malicious devices and preserves safe argv')


def test_qos(sh, temporary):
    temporary.mkdir(parents=True, exist_ok=True)
    hnat = temporary / 'hnat'
    hnat.mkdir(exist_ok=True)
    source = read(MTK / 'luci-app-eqos-mtk/root/usr/sbin/eqos')
    # Relocate device filesystem writes and stub networking tools, then run real stop.
    source = source.replace('/sys/kernel/debug/hnat', hnat.as_posix())
    source = source.replace('/etc/firewall.user', (temporary / 'firewall.user').as_posix())
    stubs = '\n'.join(f'{name}() {{ :; }}' for name in
                      ('tc', 'ip', 'iptables', 'ip6tables', 'ebtables', 'sed'))
    # Minimal Git for Windows does not bundle seq; emulate this standard utility.
    stubs += '\nseq() { local n=$1; while [ "$n" -le "$2" ]; do echo "$n"; n=$((n+1)); done; }'
    script = temporary / 'eqos-test.sh'
    script.write_text(stubs + '\n' + source, encoding='utf-8', newline='\n')
    subprocess.run([sh, '-n', str(script)], check=True)
    subprocess.run([sh, str(script), 'stop'], check=True, capture_output=True)
    for index in range(64):
        expected = f'{0 if index < 32 else 1} 0 0 0 0 4 4'
        assert (hnat / f'qdma_txq{index}').read_text().strip() == expected
    for relative in ('mtwifi-cfg/files/netifd/mtwifi.sh',):
        subprocess.run([sh, '-n', str(MTK / relative)], check=True)
    print('PASS: EQoS stop resets all 64 hardware queues; modified shell syntax valid')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sh', required=True)
    parser.add_argument('--tmp', type=Path, required=True)
    args = parser.parse_args()
    test_wireless()
    test_legacy()
    test_qos(args.sh, args.tmp.resolve())
