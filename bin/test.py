#!/usr/bin/env python
"""
Copyright 2013 Intel Corporation All Rights Reserved.

The source code, information and material ("Material") contained
herein is owned by Intel Corporation or its suppliers or licensors,
and title to such Material remains with Intel Corporation or its
suppliers or licensors. The Material contains proprietary information
of Intel or its suppliers and licensors. The Material is protected by
worldwide copyright laws and treaty provisions. No part of the
Material may be used, copied, reproduced, modified, published,
uploaded, posted, transmitted, distributed or disclosed in any way
without Intel's prior express written permission.

No license under any patent, copyright or other intellectual property
rights in the Material is granted to or conferred upon you, either
expressly, by implication, inducement, estoppel or otherwise. Any
license under such intellectual property rights must be express and
approved by Intel in writing.

Unless otherwise agreed by Intel in writing, you may not remove or
alter this notice or any other notice embedded in Materials by Intel
or Intel's suppliers or licensors in any way.
"""


import sys
import encodings

if sys.hexversion < 0x02050000:
    sys.stderr.write("Python %d.%d is not supported...\n" %
        (sys.version_info.major, sys.version_info.minor))
    sys.exit(2)

if sys.hexversion < 0x03030000:
    def b(x):
        return x
    def decode(x):
        return x
    def encode(x):
        return x
else:
    import codecs
    def b(x):
        return codecs.latin_1_encode(x)[0]
    def decode(x):
        return x.decode()
    def encode(x):
        return x.encode()

import os
import glob
import re
import shutil
import subprocess
import tempfile
import signal
from optparse import OptionParser, OptionGroup
import logging
import threading
import getpass
import zipfile

CREATE_NEW_PROCESS_GROUP=0x00000200
DETACHED_PROCESS = 0x00000008

#Ignore SIGINT signal by setting the handler to SIG_IGN
def preexec_signal_function():
    signal.signal(signal.SIGINT, signal.SIG_IGN)

class ProgressBar:
    def __init__(self, message):
        self.message = message
        self.slash = ["-", "\\", "|", "/"]
        self.state = 0
        sys.stdout.write(message + ' ' + self.slash[self.state])
        sys.stdout.flush()
        self.timer = None

    def start(self):
        self.timer = threading.Timer(1, self._update)
        self.timer.daemon = True
        self.timer.start()

    def stop(self):
        self.timer.cancel()
        sys.stdout.write("\n")

    def _update(self):
        self.state = (self.state + 1) % len(self.slash)
        sys.stdout.write("\b" + self.slash[self.state])
        sys.stdout.flush()
        # self.start()

class EmptyProgressBar:
    def __init__(self, message):
        self.empty = None

    def start(self):
        self.empty = None

    def stop(self):
        self.empty = None

    def _update(self):
        self.empty = None

class MessageWriter:
    def __init__(self, xml = False):
        self.xml = xml
        if self.xml:
            sys.stderr.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            sys.stderr.write("<feedback>")

    def finalize(self):
        if self.xml:
            sys.stderr.write("</feedback>")

    def write(self, message, severity="error"):
        if not self.xml:
            sys.stderr.write(severity.upper() + ": " + message)
        else:
            sys.stderr.write("<message severity=\""+ severity + "\">%s</message>\n<nop/>" % message.strip())
        sys.stderr.flush()

class ProductLayout:
    def __init__(self, install_dir, project_dir, tmp_dir):
        self.install_dir = os.environ.get("AMPLXE_TARGET_PRODUCT_DIR", install_dir)
        if self.install_dir[-1] != '/': self.install_dir += '/'

        self.tmp_dir = os.environ.get("AMPLXE_TARGET_TMP_DIR", tmp_dir)
        if self.tmp_dir[-1] != '/': self.tmp_dir += '/'

        self.project_dir = os.environ.get("AMPLXE_TARGET_PROJECT_DIR", project_dir)
        if self.project_dir[-1] != '/': self.project_dir += '/'

        self.lib32_dir = self.install_dir + "lib32/"
        self.bin32_dir = self.install_dir + "bin32/"
        self.drv32_dir = self.install_dir + "drv32/"
        self.lib64_dir = self.install_dir + "lib64/"
        self.bin64_dir = self.install_dir + "bin64/"
        self.drv64_dir = self.install_dir + "drv64/"
        self.prefix = "amplxe"

    def get_bin32_dir(self):
        return self.bin32_dir

    def get_lib32_dir(self):
        return self.lib32_dir

    def get_drv32_dir(self):
        return self.drv32_dir

    def get_bin64_dir(self):
        return self.bin64_dir

    def get_lib64_dir(self):
        return self.lib64_dir

    def get_drv64_dir(self):
        return self.drv64_dir

    def get_tmp_dir(self):
        return self.tmp_dir

    def get_project_dir(self):
        return self.project_dir

    def get_install_dir(self):
        return self.install_dir

    def get_binary_path(self, name, arch):
        if arch == "k1om":
            return self.bin64_dir + self.prefix + '-' + name
        elif arch == "x86_64":
            return self.bin64_dir + self.prefix + '-' + name
        else:
            return self.bin32_dir + self.prefix + '-' + name

    def get_driver_path(self, name, arch):
        if arch == "k1om":
            return self.drv64_dir + name + '.ko'
        elif arch == "x86_64":
            return self.drv64_dir + name + '.ko'
        else:
            return self.drv32_dir + name + '.ko'

class LinuxProductLayout(ProductLayout):
    def __init__(self, options):
        install_dir = options.install_dir if options.install_dir else "/opt/intel/vtune_amplifier_xe_2013/"
        project_dir = "/tmp/results/"
        tmp_dir = "/tmp/"
        ProductLayout.__init__(self, install_dir, project_dir, tmp_dir)

    def get_sysmodule_pattern(self):
        return re.compile("|".join(["^/bin/", "^/lib/", "^/lib32/", "^/lib64/",
            "^/usr/", "^/sbin/", "^/etc/", "^vmlinux$"]))

    def get_layout_name(self):
        return 'linux'

class MICProductLayout(ProductLayout):
    def __init__(self):
        install_dir = "/amplxe/"
        project_dir = "/amplxe/results/"
        tmp_dir = "/tmp/"
        ProductLayout.__init__(self, install_dir, project_dir, tmp_dir)

    def get_sysmodule_pattern(self):
        return re.compile("|".join(["^/tmp/"]))

    def get_layout_name(self):
        return 'mic'

class AndroidProductLayout(ProductLayout):
    def __init__(self):
        pckg_dir = "/data/data/com.intel.vtune"
        install_dir = pckg_dir + "/perfrun"
        project_dir = pckg_dir + "/results"
        tmp_dir     = pckg_dir + "/tmp"
        ProductLayout.__init__(self, install_dir, project_dir, tmp_dir)

    def get_sysmodule_pattern(self):
        return re.compile("|".join(["^/system/", "^vmlinux$"]))

    def get_layout_name(self):
        return 'android'

class RemoteShell:
    def __init__(self):
        self.devnull = open(os.devnull, "w")

        #exclude interrupts loops
        self.firstInterrupt = True

    def chmod(self, mode, path):
        return self.call(["chmod", mode, path], silent=True)

    def ps(self, *options):
        return self.get_cmd_output(["ps"] + list(options))

    def rm(self, *options):
        return self.call(["rm"] + list(options), silent=True)

    def ls(self, *options):
        return self.get_cmd_output(["ls"] + list(options))

    def cat(self, *options):
        return self.get_cmd_output(["cat"] + list(options))

    def mkdir(self, directory):
        return self.call(["mkdir", "-p", directory], silent=True)

    def uname(self, *options):
        uname_output = self.get_cmd_output(["uname"] + list(options))
        return uname_output[0]

    def call(self, args, silent=False, **kwargs):
        if silent:
            cout, cerr = tempfile.TemporaryFile(), tempfile.TemporaryFile()
            retcode = self._call_shell(args, stdout=cout, stderr=cerr, **kwargs)
            cout.seek(0); logging.debug("call stdout: %s" % cout.read().splitlines())
            cerr.seek(0); logging.debug("call stderr: %s" % cerr.read().splitlines())
        else:
            retcode = self._call_shell(args, **kwargs)

        return retcode

    def get_cmd_output(self, args):
        cout, cerr = tempfile.TemporaryFile(), tempfile.TemporaryFile()
        self._call_shell(args, stdout=cout, stderr=cerr)
        cout.seek(0); logging.debug("get_cmd_output stdout: %s" % cout.read().splitlines())
        cerr.seek(0); logging.debug("get_cmd_output stderr: %s" % cerr.read().splitlines())

        cout.seek(0)
        cerr.seek(0)
        output = cout.read().splitlines() + cerr.read().splitlines()
        return [decode(x.strip()) for x in output if x]

    def _call_cygpath(self, args):
        if not sys.platform in ['win32', 'cygwin']:
            return args
        try:
            command = ["cygpath", args]
            process = subprocess.Popen(command, stdout=subprocess.PIPE)
            stdout, stderr = process.communicate()
            retcode = process.poll()
            if retcode:
                raise subprocess.CalledProcessError(retcode, command)
            return stdout.strip()
        except:
            return args

    def _call_winpath(self, args):
        if not sys.platform in ['cygwin']:
            return args
        try:
            command = ["cygpath", "-w", args]
            process = subprocess.Popen(command, stdout=subprocess.PIPE)
            stdout, stderr = process.communicate()
            retcode = process.poll()
            if retcode:
                raise subprocess.CalledProcessError(retcode, command)
            return stdout.strip()
        except:
            return args

class SSH(RemoteShell):
    def __init__(self, options):
        RemoteShell.__init__(self)

        #arguments to enable non-default port
        self.ssh_port_args = []
        self.scp_port_args = []
        target = options.target.split(':')
        if len(target) > 1:
            self.ssh_port_args = ["-p", target[1]]
            self.scp_port_args = ["-P", target[1]]

        options.target = self.machine = target[0]

        self.uid = None
        self.options = options

    def is_ready(self):
        if self.uid != None:
            return True
        try:
            full_output = self.get_cmd_output(["id"])
            output = full_output[0]
            m = re.match("uid=(\d+)", output)
            if m:
                self.uid = int(m.group(0).replace("uid=", ''))
                return True
            else:
                self.options.messenger.write("ssh - " + " ".join(full_output) + "\n")
                return False
        except:
            return False

    def is_root(self):
        if self.uid != None:
            return self.uid == 0
        try:
            output = self.get_cmd_output(["id"])[0]
            if re.match("uid=0", output):
                self.uid = 0
                return True
            else:
                return False
        except:
            return False

    def pull(self, src, dest):
        machine_src = self.machine + ":" + src
        dest = self._call_cygpath(dest)
        retcode = self._call_scp([machine_src, dest])
        if retcode != 0:
            retcode = self._call_scp(["-r", machine_src + "/*", dest])
        return retcode

    def rpull(self, src, dest):
        machine_src = self.machine + ":" + src
        dest = self._call_cygpath(dest)
        return self._call_scp(["-r", machine_src + "/*", dest])

    def push(self, src, dest):
        machine_dest = self.machine + ":" + dest
        src = self._call_cygpath(src)
        retcode =  self._call_scp(["-r", src, machine_dest])
        return retcode

    def serialno(self):
        hostname_output = self.get_cmd_output(["hostname"])
        return hostname_output[0]

    def _call_scp(self, args):
        logging.info("call scp %s", args)

        cout, cerr = tempfile.TemporaryFile(), tempfile.TemporaryFile()
        retcode = subprocess.call(["scp", "-B"] + self.scp_port_args + args, stdout=cout, stderr=cerr)
        cout.seek(0); logging.debug("_call_scp stdout: %s" % cout.read().splitlines())
        cerr.seek(0); logging.debug("_call_scp stderr: %s" % cerr.read().splitlines())

        return retcode

    def _call_shell(self, args, without_logs=False, **kwargs):
        if not without_logs:
            logging.info("call ssh %s", args)

        def threaded_function(results, args, kwargs):
            default_args = ["-o", "BatchMode=yes", self.machine] + self.ssh_port_args

            if 'stdout' in kwargs.keys() or 'stderr' in kwargs.keys():
                process = subprocess.Popen(["ssh"] + default_args + args, **kwargs)
                stdout, stderr = process.communicate()
            else:
                process = subprocess.Popen(["ssh"] + default_args + args,
                    stderr=subprocess.PIPE,
                    **kwargs)
                line = process.stderr.readline()
                while line:
                    #need to remove feedback and xml to have one session per amplxe-runss.py run
                    line = line.replace('<?xml version=\"1.0\" encoding=\"UTF-8\"?>', '')
                    line = line.replace('<feedback>', '')
                    line = line.replace('<feedback/>', '')
                    line = line.replace('</feedback>', '')

                    sys.stderr.write(line)
                    sys.stderr.flush()
                    line = process.stderr.readline()
                process.communicate()
            results[0] = process.poll()

        results = [None]
        #disable ctrl+c for child processes
        if sys.platform == 'win32':
            kwargs.update(creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS)
        else:
            kwargs.update(preexec_fn = preexec_signal_function)

        thread = threading.Thread(target = threaded_function, args = (results, args, kwargs))
        thread.start()

        self.firstInterrupt = True
        while True:
            try:
                if thread.isAlive():
                    thread.join(1)
                else:
                    break
            except KeyboardInterrupt:
                if self.firstInterrupt:
                    colector_cmd = []
                    try:
                        result_dir = args[args.index("--result-dir") + 1]
                        for arg in args:
                            if "-runss" in arg:
                                 index = args.index(arg)
                                 colector_cmd = args[:index + 1] + ["--result-dir", result_dir, "--command", "stop"]
                                 break
                        self.firstInterrupt = False
                    except:
                        return 1
                    if len(colector_cmd) > 0:
                        self.options.messenger.write("CTRL-C signal received.\n", "info")
                        self._call_shell(colector_cmd, without_logs=True)

        return results[0]

class Putty(RemoteShell):
    def __init__(self, options):
        RemoteShell.__init__(self)

        #arguments to enable non-default port
        self.port_args = []
        target = options.target.split(':')
        if len(target) > 1:
            self.port_args = ["-P", target[1]]

        options.target = self.machine = target[0]

        self.uid = None
        self.options = options

    def is_ready(self):
        if self.uid != None:
            return True
        try:
            full_output = self.get_cmd_output(["id"])
            if len(full_output) > 0:
                output = full_output[0]
            else:
                output = ""
            m = re.match("uid=(\d+)", output)
            if m:
                self.uid = int(m.group(0).replace("uid=", ''))
                return True
            else:
                full_output = " ".join(full_output)
                if full_output == '':
                    full_output = self.get_cmd_output([])
                    self.options.messenger.write("plink - " + " ".join(full_output) + " Probably non-password access was not set\n")
                else:
                    self.options.messenger.write("plink - " + full_output + "\n")
                return False
        except:
            return False

    def is_root(self):
        if self.uid != None:
            return self.uid == 0
        try:
            output = self.get_cmd_output(["id"])[0]
            if re.match("uid=0", output):
                self.uid = 0
                return True
            else:
                return False
        except:
            return False

    def pull(self, src, dest):
        machine_src = self.machine + ":" + src
        retcode = self._call_scp([machine_src, dest])
        if retcode != 0:
            retcode = self._call_scp(["-r", machine_src + "/*", dest])
        return retcode

    def rpull(self, src, dest):
        machine_src = self.machine + ":" + src
        return self._call_scp(["-r", machine_src + "/*", dest])

    def push(self, src, dest):
        machine_dest = self.machine + ":" + dest
        retcode =  self._call_scp(["-r", src, machine_dest])
        return retcode

    def serialno(self):
        hostname_output = self.get_cmd_output(["hostname"])
        return hostname_output[0]

    def _call_scp(self, args):
        logging.info("call pscp %s", args)

        cout, cerr = tempfile.TemporaryFile(), tempfile.TemporaryFile()
        retcode = subprocess.call(["pscp", "-batch"] + self.port_args + args, stdout=cout, stderr=cerr)
        cout.seek(0); logging.debug("_call_scp stdout: %s" % cout.read().splitlines())
        cerr.seek(0); logging.debug("_call_scp stderr: %s" % cerr.read().splitlines())

        return retcode

    def _call_shell(self, args, without_logs=False, **kwargs):
        if not without_logs:
            logging.info("call plink %s", args)

        def threaded_function(results, args, kwargs):
            default_args = ["-batch"] + self.port_args + [self.machine]

            if 'stdout' in kwargs.keys() or 'stderr' in kwargs.keys():
                process = subprocess.Popen(["plink"] + default_args + args, **kwargs)
                stdout, stderr = process.communicate()
            else:
                process = subprocess.Popen(["plink"] + default_args + args,
                    stderr=subprocess.PIPE, **kwargs)
                line = process.stderr.readline()
                while line:
                    #need to remove feedback and xml to have one session per amplxe-runss.py run
                    line = line.replace('<?xml version=\"1.0\" encoding=\"UTF-8\"?>', '')
                    line = line.replace('<feedback>', '')
                    line = line.replace('<feedback/>', '')
                    line = line.replace('</feedback>', '')

                    sys.stderr.write(line)
                    sys.stderr.flush()
                    line = process.stderr.readline()
                process.communicate()
            results[0] = process.poll()

        results = [None]
        #disable ctrl+c for child processes
        if sys.platform == 'win32':
            kwargs.update(creationflags=CREATE_NEW_PROCESS_GROUP)
        else:
            kwargs.update(preexec_fn = preexec_signal_function)

        thread = threading.Thread(target = threaded_function, args = (results, args, kwargs))
        thread.start()

        self.firstInterrupt = True
        while True:
            try:
                if thread.isAlive():
                    thread.join(1)
                else:
                    break
            except KeyboardInterrupt:
                if self.firstInterrupt:
                    colector_cmd = []
                    try:
                        result_dir = args[args.index("--result-dir") + 1]
                        for arg in args:
                            if "-runss" in arg:
                                 index = args.index(arg)
                                 colector_cmd = args[:index + 1] + ["--result-dir", result_dir, "--command", "stop"]
                                 break
                        self.firstInterrupt = False
                    except:
                        return 1
                    if len(colector_cmd) > 0:
                        self.options.messenger.write("CTRL-C signal received.\n", "info")
                        self._call_shell(colector_cmd, without_logs=False)

        return results[0]

class ADB(RemoteShell):
    def __init__(self, options, status_dir = "/data/data/com.intel.vtune"):
        RemoteShell.__init__(self)

        self.options = options
        self.uid = None
        self.status_dir = status_dir
        self.device_arch = None #x86, arm, mips

    def is_ready(self):
        self.is_root()
        if self.uid != None:
            return True
        try:
            tmp_log = tempfile.TemporaryFile()
            retcode = self._call_adb(['shell', 'id'], stdout=tmp_log,
                stderr=tmp_log)
            tmp_log.seek(0)
            output = " ".join([decode(x.strip()) for x in tmp_log.readlines() if x])
            if retcode != 0:
                self.options.messenger.write(re.sub('error: ', 'adb - ', output) + "\n")
                return False
            m = re.match("uid=(\d+)", output)
            if m:
                self.uid = int(m.group(0).replace("uid=", ''))
                return True
            else:
                return False
        except:
            return False

    def is_root(self):
        if self.uid != None:
            return self.uid == 0
        try:
            tmp_log = tempfile.TemporaryFile()
            retcode = self._call_adb(['shell', 'su', '-c', 'id', ';', 'id', ';', 'getprop', 'ro.product.cpu.abi', ';', 'getprop', 'ro.debuggable'], stdout=tmp_log,
                stderr=tmp_log)
            tmp_log.seek(0)
            output = [decode(x.strip()) for x in tmp_log.readlines() if x]
            try:
                if 'armeabi' in output[2]:
                    self.device_arch = 'arm'
                    #don't need rooted arm
                    self.uid = 1
                    return False
                elif 'x86' in output[2]:
                    self.device_arch = 'x86'
                else:
                    self.device_arch = None
            except:
                self.device_arch = None

            if len(output) > 1 and output[0] == output[1]:
                self.uid = 0
                return True
            else:
                output = " ".join(output)
                if 'error:' in output:
                    return False
                elif 'su: not found' in output:
                    self.uid = 1
                    return False
                else:
                    #check if "adb root" is allowed
                    if output[len(output)-1] == '1':
                        self.options.messenger.write(message = "trying to root the device\n", severity = "info")
                        self._call_adb(['root'], stdout=tmp_log,
                            stderr=tmp_log)

                        tmp_log = tempfile.TemporaryFile()
                        self._call_adb(['wait-for-device', 'shell', 'id'], stdout=tmp_log,
                            stderr=tmp_log)
                        tmp_log.seek(0)
                        output = [decode(x.strip()) for x in tmp_log.readlines() if x]
                        m = re.match("uid=(\d+)", " ".join(output))
                        if m:
                            self.uid = int(m.group(0).replace("uid=", ''))
                        return self.uid == 0
                    else:
                        self.uid = 1
                        return False
        except:
            return False

    def get_devices(self, xml):
        logging.debug("call adb devices")
        process = subprocess.Popen(["adb", "devices"], stdout=subprocess.PIPE)
        stdout, stderr = process.communicate()
        retcode = process.poll()
        if retcode:
            raise subprocess.CalledProcessError(retcode, command)

        adbOutput = stdout.strip().split()
        lt =  ''
        gt = '\n'
        if xml:
            lt = "&lt;device&gt;"
            gt = "&lt;/device&gt;\n"
            sys.stderr.write("\n<data>&lt;?xml version=&quot;1.0&quot; encoding=&quot;UTF-8&quot;?&gt;\n&lt;bag&gt;\n")

        for i in xrange(len(adbOutput)):
            if adbOutput[i] == 'device' and i > 1:
                sys.stderr.write(lt + adbOutput[i - 1].strip() + gt)
        if xml:
            sys.stderr.write("&lt;/bag&gt;\n</data>\n<nop/>\n")

    def install(self, apk):
        tmp_log = tempfile.TemporaryFile()
        retcode = self._call_adb(["install", self._call_winpath(apk)], stdout=tmp_log,
            stderr=tmp_log)

        tmp_log.seek(0)
        for line in tmp_log.readlines():
            if 'Fail' in decode(line.strip()):
                sys.stdout.write("Could not install apk file.\n")
                sys.stdout.write("Check 'adb install %s' command" % apk)
                sys.exit(1)
            logging.debug(line.strip())
        return retcode

    def uninstall(self, package):
        tmp_log = tempfile.TemporaryFile()
        retcode = self._call_adb(["uninstall", package], stdout=tmp_log,
            stderr=tmp_log)

        tmp_log.seek(0)
        for line in tmp_log.readlines():
            logging.debug(line)
        return retcode

    def am_start(self, activity):
        tmp_log = tempfile.TemporaryFile()
        retcode = self._call_adb(["shell", "am", "start", "-W", "-n", activity], stdout=tmp_log,
            stderr=tmp_log)

        tmp_log.seek(0)
        for line in tmp_log.readlines():
            logging.debug(line)
        return retcode

    def am_force_stop(self, package):
        tmp_log = tempfile.TemporaryFile()
        retcode = self._call_adb(["shell", "am", "force-stop", package], stdout=tmp_log,
            stderr=tmp_log)

        tmp_log.seek(0)
        for line in tmp_log.readlines():
            logging.debug(line.strip())
        return retcode

    def pull(self, src, dest):
        retcode = self._call_adb(["pull", src, self._call_winpath(dest)], stdout=self.devnull,
            stderr=self.devnull)
        return retcode

    def rpull(self, src, dest):
        return self.pull(src, dest)

    def push(self, src, dest,):
        tmp_log = tempfile.TemporaryFile()
        retcode = self._call_adb(["push", self._call_winpath(src), dest], stdout=tmp_log,
            stderr=tmp_log)

        tmp_log.seek(0)
        for line in tmp_log.readlines():
            logging.debug(line)
        return retcode

    def serialno(self):
        logging.debug("call adb get-serialno")
        command = ["adb", "get-serialno"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE)
        stdout, stderr = process.communicate()
        retcode = process.poll()
        if retcode:
            raise subprocess.CalledProcessError(retcode, command)
        return stdout.strip()

    def get_arch(self):
        return self.device_arch

    def is_otc(self):
        if 'No such file or directory' in str(self.ls('/system/lib/modules')):
            return False
        return True

    def _call_shell(self, args, **kwargs):
        is_root = self.is_root()

        runss_mode = False
        if 'runss.sh' in " ".join(args):
            runss_mode = True

        errorfile = '/data/amplxe-errorlevel'
        stdoutfile= '/data/amplxe-stdout'
        if not is_root:
            errorfile = self.status_dir + '/amplxe-errorlevel'
            stdoutfile =  self.status_dir + '/amplxe-stdout'

        errorlevelcmd = ['echo', '$?','>', errorfile]
        if len(args) and args[len(args) - 1] != ';':
            errorlevelcmd = [';'] + errorlevelcmd

        run_as = []
        if runss_mode:
            args += ['>', stdoutfile]
        self._call_adb(["shell"] + run_as + args + errorlevelcmd,  **kwargs)

        #get return code
        process = subprocess.Popen(['adb', 'shell'] + run_as + ['cat', errorfile], stdout=subprocess.PIPE)
        stdout, stderr = process.communicate()
        retcode = process.poll()
        if retcode:
            self.options.messenger.write("Connection was lost.\n")
            sys.exit(1)
        logging.info("call adb return code %s", stdout.strip())

        if runss_mode:
            process = subprocess.Popen(['adb', 'shell', 'cat', stdoutfile], **kwargs)
            process.communicate()
            retcode = process.poll()
        try:
            ret_code = int(stdout.strip())
        except:
            #that means that file is absent and product is not instlled or old
            self.options.messenger.write("Could not find product on device. Automatic installation...\n", "info")
            logging.info("Could not find product on device. Automatic installation...")
            installer = AndroidPackageInstaller(self.options)
            installer.clean()
            installer.install()
            return self._call_shell(args, **kwargs)
        return ret_code

    def _call_adb(self, args, without_logs=False, **kwargs):
        if not without_logs:
            logging.info("call adb %s", args)

        def threaded_function(results, args, kwargs):

            if 'stdout' in kwargs.keys() or 'stderr' in kwargs.keys():
                process = subprocess.Popen(["adb"] + args, **kwargs)
                stdout, stderr = process.communicate()
            else:
                process = subprocess.Popen(["adb"] + args,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    **kwargs)
                line = process.stdout.readline()
                while line:
                    #need to remove feedback and xml to have one session per amplxe-runss.py run
                    line = line.replace('<?xml version=\"1.0\" encoding=\"UTF-8\"?>', '')
                    line = line.replace('<feedback>', '')
                    line = line.replace('<feedback/>', '')
                    line = line.replace('</feedback>', '')

                    split_line = line.lower().split()
                    if 'segmentation' in split_line or 'error:' in split_line:
                        self.options.messenger.write("target - %s\n" % line, "info")

                    sys.stderr.write(line)
                    sys.stderr.flush()
                    line = process.stdout.readline()
                process.communicate()
            results[0] = process.poll()

        results = [None]
        #disable ctrl+c for child processes
        if sys.platform == 'win32':
            kwargs.update(creationflags=CREATE_NEW_PROCESS_GROUP)
        else:
            kwargs.update(preexec_fn = preexec_signal_function)

        thread = threading.Thread(target = threaded_function, args = (results, args, kwargs))
        thread.start()

        self.firstInterrupt = True
        while True:
            try:
                if thread.isAlive():
                    thread.join(1)
                else:
                    break
            except KeyboardInterrupt:
                if self.firstInterrupt:
                    colector_cmd = []
                    try:
                        result_dir = args[args.index("--result-dir") + 1]
                        for arg in args:
                            if "-runss.sh" in arg:
                                 index = args.index(arg)
                                 colector_cmd = args[:index + 1] + ["--result-dir", result_dir, "--command", "stop"]
                                 break
                        self.firstInterrupt = False
                    except:
                        return 1
                    if len(colector_cmd) > 0:
                        self.options.messenger.write("CTRL-C signal received.\n", "info")
                        self._call_adb(colector_cmd, without_logs=False)

        return results[0]

def path_split(path):
    path = path.replace('\\', '/')
    return path.split('/')

class AndroidPackageInstaller:
    def __init__(self, options):
        self.options = options

        self.is_local_prop_modified = False

        if not hasattr(self.options, 'messenger'):
            self.options.messenger = MessageWriter(xml=False)

        try:
            self.options.option_file
            self.empty_progress = True
        except:
            self.empty_progress = False

        script_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        try:
             log_dir = os.path.dirname(self.options.log_name)
        except:
            log_dir = script_dir
            log_name = "setup.%s.log" % os.getpid()
            full_log_name = os.path.join(log_dir, log_name)
            if not self._is_writable(full_log_name):
                log_dir = ''
                full_log_name = os.path.join(log_dir, log_name)
            if not self._is_writable(full_log_name):
                self.options.messenger.write("Installation is fail because current directory is not writable. Change directory.\n")
                sys.exit(1)

            logging.basicConfig(filename=full_log_name, level=logging.DEBUG, filemode="w")

        self.adb = ADB(self.options)

        if not self.options.package_command == 'build':
            self._check_adb()

        apk_file_dirs = [
                            script_dir,
                            os.path.join(script_dir, '..', 'target'),
                            os.path.join(script_dir, '..', 'target', 'android'),
                            os.path.join(script_dir, '..', 'target', 'android_arm'),
                        ]

        if 'install' not in script_dir:
            script_dir = os.path.abspath(os.path.curdir)

            if 'vcs' in script_dir:
                parts = path_split(script_dir)
                parts = parts[:parts.index('vcs')]
                script_dir = os.path.sep.join(parts + ['install'])
            else:
                dir = os.path.join(script_dir, 'install')
                if os.path.exists(dir):
                    script_dir = dir

        path_parts = path_split(script_dir)
        if 'install' in path_parts:
            path_parts = path_parts[:path_parts.index('install') + 1]
            apk_file_dirs += [
                                script_dir,
                                os.path.sep.join(path_parts + ['target']),
                                os.path.sep.join(path_parts + ['target', 'android']),
                                os.path.sep.join(path_parts + ['target', 'android_arm']),
                            ]

        self.vtune_pkg_name='com.intel.vtune'
        self.apk_file = None

        apk_ext = '.apk'
        if not self.adb.get_arch() in [None, 'x86']:
            apk_ext = '.' + self.adb.get_arch() + '.apk'

        for apk_file_dir in apk_file_dirs:
            apk_file = os.path.join(apk_file_dir, self.vtune_pkg_name + apk_ext)
            if os.path.isfile(apk_file):
                self.apk_file = os.path.normpath(apk_file)
                self.pkg_root_dir = os.path.dirname(self.apk_file)
                break

        if self.apk_file is None:
            self.options.messenger.write("Could not find " + self.vtune_pkg_name + " apk file to install package. Check target dir.\n")
            sys.exit(1)

        self.product = AndroidProductLayout()
        self.build_dir = os.path.join(log_dir, ".cache")
        self.install_dir = self.build_dir + self.product.get_install_dir()
        if not os.path.exists(self.build_dir):
            logging.info("Creating %s empty directory" % self.build_dir)
            os.makedirs(self.build_dir)
            logging.info("Creating %s empty directory" % self.install_dir)
            os.makedirs(self.install_dir)

    def install(self):
        try:
            build_drv = self.options.build_drivers
        except:
            build_drv = False

        self.uninstall()
        self._check_adb()
        if self.apk_file is None:
            self._check_adb_root()

        is_root = self.adb.is_root()

        self.build()

        serialno = self.adb.serialno()
        if self.adb.get_arch() != 'x86':
            self.options.messenger.write("Device isn't x86 architecure - sytem-wide and pmu-events collections will be not available\n", "info")
            logging.info("Device isn't x86 architecure - sytem-wide and pmu-events collections will be not available")
        elif not is_root:
            self.options.messenger.write("Device isn't in root mode - sytem-wide and pmu-events collections will be not available\n", "info")
            logging.info("Device isn't in root mode - sytem-wide and pmu-events collections will be not available")
        if self.empty_progress:
            progressbar = EmptyProgressBar("")
            self.options.messenger.write(message = "Installing the package to %s\n" % serialno, severity = "info")
        else:
            progressbar = ProgressBar("Installing the package to %s:" % serialno)
        logging.info("Installing the package to %s\n" % serialno)

        progressbar.start()

        if self.apk_file is not None:
            self.adb.install(self.apk_file)
            self.adb.am_start(self.vtune_pkg_name + "/" + self.vtune_pkg_name + ".MainActivity")
            self.adb.am_force_stop(self.vtune_pkg_name)

        if is_root:
            if self.adb.is_otc() or self.adb.get_arch() == 'arm':
                local_prop = os.path.join(self.build_dir, "data", "local.prop")
                shutil.move(local_prop, local_prop + '_jitvtuneinfo')
                self.adb.push(self.build_dir, "/")
                shutil.move(local_prop + '_jitvtuneinfo', local_prop)
                self.is_local_prop_modified = False
            else:
                self.adb.push(self.build_dir, "/")
                self.adb.chmod("0644", "/data/local.prop")
            self.adb.chmod("0777", self.product.get_project_dir())
            self.adb.chmod("0777", '/data/amplxe/results')
            if self.apk_file is None:
                self.adb.chmod("0775", self.product.get_bin32_dir() + '*')

        progressbar.stop()
        if is_root and self.adb.get_arch() == 'x86' and self.is_local_prop_modified:
            self.options.messenger.write("Reboot your device to have correct resolved dynamic code...\n", "info")
            logging.info("Reboot your device to have correct resolved dynamic code...")

    def uninstall(self):
        self._check_adb()
        if self.apk_file is None:
            self._check_adb_root()

        is_root = self.adb.is_root()
        if is_root:
            self.adb.rm("-r","/data/amplxe/results/")
            self.adb.rm("-r", self.product.get_project_dir())
            self.adb.rm("/data/intel/libittnotify.so")
        if self.apk_file is not None:
            self.adb.uninstall(self.vtune_pkg_name)
        elif is_root:
            self.adb.rm("/data/data/" + self.vtune_pkg_name + "/perfrun")
            self.adb.rm("-r", self.product.get_install_dir())

    def clean(self):
        self.options.messenger.write("Deleting '%s' directory\n" % self.build_dir, "info")
        logging.info("Deleting '%s' directory\n" % self.build_dir)
        shutil.rmtree(self.build_dir, True)

    def build(self):
        try:
            build_drv = self.options.build_drivers
        except:
            build_drv = False

        marker_done = os.path.join(self.build_dir, "DONE")
        if os.path.exists(marker_done):
            self._copy_libittnotify() #this workaroud while we don't change path to ittnotify in dalvik
            logging.info("DONE marker exists, nothing to do")
            return

        self.options.messenger.write("Creating '%s' directory\n" % self.build_dir, "info")
        logging.info("Creating '%s' directory" % self.build_dir)
        self._create_local_prop()
        self._create_results_dir()
        self._copy_libittnotify()
        if self.apk_file is None:
            self._create_tmp_dir()
            self._copy_bin32_dir()
            self._copy_lib32_dir()
            self._copy_config()
            self._copy_message_dir()
            self._copy_doc_dir()
        drivers = []
        if build_drv and self.adb.get_arch() in [None, 'x86']:
            drivers += self._build_sepdk()
            #disable power support
            #drivers += self._build_pwrdk()

        self._create_drv32_dir(drivers)

        open(marker_done, "w")
        logging.info("creating DONE marker file")

    def _is_writable(self, path):
        try:
            f = open(path,'w')
            f.close()
        except IOError:
            return False
        return True

    def _create_drv32_dir(self, driver_list):
        drv32_dir = self.build_dir + self.product.get_drv32_dir()
        os.makedirs(drv32_dir)
        for driver in driver_list:
            if os.path.isfile(driver):
                shutil.copy(driver, drv32_dir)

    def _build_sepdk(self):
        sepdk_dir=os.path.join(self.pkg_root_dir, "sepdk")
        self._build_driver("SEP/VTSS++", sepdk_dir, "VTSS=android")
        sepdk_dir=os.path.join(self.build_dir + "_sepdk", "sepdk", "src")
        return [os.path.join(sepdk_dir, "pax", "pax.ko"),
            os.path.join(sepdk_dir, "sep3_8.ko"),
            os.path.join(sepdk_dir, "sep3_10.ko"),
            os.path.join(sepdk_dir, "vtsspp", "vtsspp.ko")]

    def _build_pwrdk(self):
        pwrdk_dir=os.path.join(self.pkg_root_dir, "powerdk", "src")
        self._build_driver("WuWatch", pwrdk_dir)
        return [os.path.join(pwrdk_dir, "apwr3_1.ko")]

    def _build_driver(self, drvname, driverdk, *extra_args):

        ANDROID_KERNEL_SRC_DIR=self.options.kernel_src_dir
        KERNEL_VERSION=self.options.kernel_version

        kernel_config = os.path.join( ANDROID_KERNEL_SRC_DIR, ".config")
        kernel_arch = 'x86'
        sig_hash_algorithm=None
        if os.path.isfile(kernel_config):
            for line in open(kernel_config, "r").readlines():
                if 'Kernel Configuration' in line:
                    if 'x86_64' in line:
                        kernel_arch = 'x86_64'
                    if KERNEL_VERSION=='unknown':
                        KERNEL_VERSION=line.split()[2]

                elif 'CONFIG_MODULE_SIG_HASH=' in line:
                    sig_hash_algorithm = re.search("CONFIG_MODULE_SIG_HASH=(.+)", line)
                    if sig_hash_algorithm:
                        sig_hash_algorithm = sig_hash_algorithm.group(1)
                    else:
                        sig_hash_algorithm=None


        #copy driverdk to local .cache

        shutil.rmtree(self.build_dir + '_' + os.path.basename(driverdk), True)
        sepdk = os.path.join(self.build_dir + '_' + os.path.basename(driverdk), os.path.basename(driverdk))
        shutil.copytree(driverdk, sepdk)

        src_dir = os.path.join(sepdk, 'src')
        if not os.path.exists(src_dir):
            shutil.copytree(driverdk, os.path.join(os.path.join(sepdk, 'src')))

        if kernel_arch=='x86': #mcg
            ARCH= "MARCH=i386"
            if os.path.exists(os.path.join(src_dir, 'Makefile.android')):
                for make_dir in ['', 'pax']:
                    shutil.copy(os.path.join(src_dir, make_dir, 'Makefile.android'), os.path.join(src_dir, make_dir, 'Makefile'))
        else: #otc
            ARCH = "ARCH=x86_64"

        driverdk = src_dir

        if not ANDROID_KERNEL_SRC_DIR:
            #backward compatibility
            ANDROID_REPO=os.environ.get("ANDROID_REPO")
            PRODUCT=os.environ.get("PRODUCT")

            if not PRODUCT or not ANDROID_REPO:
                self.options.messenger.write("Please set option value --kernel-src-dir.\n");
                self.options.messenger.write("For example, --kernel-src-dir=path_to_src_tree/out/target/product/ctp_pr1/kernel_build\n")
                sys.exit(2)

            ANDROID_REPO=os.path.abspath(ANDROID_REPO)
            ANDROID_KERNEL_SRC_DIR=os.path.join(ANDROID_REPO, "out", "target", "product", PRODUCT, "kernel_build")
        else:
            ANDROID_KERNEL_SRC_DIR=os.path.abspath(ANDROID_KERNEL_SRC_DIR)

        if os.path.isdir(ANDROID_KERNEL_SRC_DIR):
            make_log = tempfile.TemporaryFile()
            if self.empty_progress:
                processbar = EmptyProgressBar("")
                self.options.messenger.write(message = "Building %s driver\n" % drvname, severity = "info")
            else:
                processbar = ProgressBar("Building %s driver:" % drvname)

            processbar.start()
            driver_subdirs = ['.', 'pax', 'vtsspp']
            if kernel_arch=='x86': #mcg
                driver_subdirs = ['.']
            for driver_subdir in driver_subdirs:
                make_driver = ["make", "-C", os.path.join(driverdk, driver_subdir), "KERNEL_VERSION=" + KERNEL_VERSION,
                    "KERNEL_SRC_DIR=" + ANDROID_KERNEL_SRC_DIR, ARCH] + list(extra_args)
                subprocess.check_call(make_driver + ["clean"], stdout=make_log, stderr=make_log)
                try:
                    subprocess.check_call(make_driver, stdout=make_log, stderr=make_log)
                except:
                    self.options.messenger.write("\n\ncould not build driver. Could you check 'make' command?\n")
                    sys.stderr.write("%s\n\n" % " ".join(make_driver))
                    subprocess.call(make_driver)
                    sys.exit(1)

            processbar.stop()

            make_log.seek(0)
            for line in make_log.readlines():
                logging.debug(line.rstrip())

            if sig_hash_algorithm is not None:
                sign_file = os.path.join(ANDROID_KERNEL_SRC_DIR, 'source', 'scripts', 'sign-file')
                if os.path.isfile(sign_file):
                    sign_driver = [
                                      sign_file,
                                      sig_hash_algorithm.replace("\"", ""),
                                      os.path.join(ANDROID_KERNEL_SRC_DIR, 'signing_key.priv'),
                                      os.path.join(ANDROID_KERNEL_SRC_DIR, 'signing_key.x509'),
                                  ]
                    for driver in ["pax/pax.ko", "sep3_10.ko", "vtsspp/vtsspp.ko"]:
                        sign_log = tempfile.TemporaryFile()
                        full_driver_path = [os.path.join(driverdk, driver)]
                        logging.debug("Sign kernel module %s" % full_driver_path)
                        logging.debug("%s" % " ".join(sign_driver + full_driver_path))
                        try:
                            subprocess.check_call(sign_driver + full_driver_path, stdout=sign_log, stderr=sign_log)
                        except:
                            self.options.messenger.write("Could not sign driver. Could you check 'sign' command?\n", "info")
                            sys.stderr.write("%s\n\n" % " ".join(sign_driver + full_driver_path))
                            subprocess.call(sign_driver + full_driver_path)

                        sign_log.seek(0)
                        for line in sign_log.readlines():
                            logging.debug(line.rstrip())
                else:
                    logging.debug("could not find %s to sign drivers" % sign_file)
        else:
            self.options.messenger.write("the script cannot build %s driver.\n" % drvname)
            self.options.messenger.write("Is correct --kernel-src-dir value '%s'?\n" % ANDROID_KERNEL_SRC_DIR)
            sys.exit(1)

    def _create_local_prop(self):
        local_prop = os.path.join(self.build_dir, "data", "local.prop")
        logging.info("creating '%s' file" % local_prop)
        os.makedirs(os.path.dirname(local_prop))
        try:
            self.adb.pull("/data/local.prop", local_prop)
        except:
            pass # it is OK for "build" action doesn't have "adb"

        try:
            self.options.jitvtuneinfo
        except:
            self.options.jitvtuneinfo = "jit"

        content = []
        is_modified = False
        if os.path.isfile(local_prop):
            for line in open(local_prop, "r").readlines():
                line = line.strip()
                if not line: continue
                if re.match("dalvik.vm.extra-opts", line):
                    jitinfo = re.search("-Xjitvtuneinfo:(\w+)", line)
                    if jitinfo:
                        jitinfo_value = jitinfo.group(1)
                        if self.options.jitvtuneinfo != None and jitinfo_value != self.options.jitvtuneinfo:
                            line = line.replace('-Xjitvtuneinfo:' + jitinfo_value, '-Xjitvtuneinfo:' + self.options.jitvtuneinfo)
                            is_modified = True
                    else:
                        if self.options.jitvtuneinfo == None:
                            self.options.jitvtuneinfo = "jit"
                        line += " -Xjitvtuneinfo:" + self.options.jitvtuneinfo
                        is_modified = True
                content += [line]
        else:
            if self.options.jitvtuneinfo == None:
                self.options.jitvtuneinfo = "jit"
            content += ["dalvik.vm.extra-opts=-Xjitvtuneinfo:" + self.options.jitvtuneinfo]
            is_modified = True

        if is_modified:
            self.is_local_prop_modified = True
            logging.info("local.prop content was modified: " + "; ".join(content))
            open(local_prop, "wb").write(encode("\n".join(content)))
        else:
            logging.info("local.prop content was not modified: " + "; ".join(content))


    def _copy_libittnotify(self):
        data_intel = os.path.join(self.build_dir, "data", "intel")
        src_ittnotify = os.path.join(self.pkg_root_dir, "lib32", "runtime",
            "libittnotify_collector.so")
        dst_ittnotify = os.path.join(data_intel, "libittnotify.so")
        try:
            self.options.use_cache
        except:
            self.options.use_cache = False

        if os.path.isfile(dst_ittnotify) and self.options.use_cache:
            return
        if not os.path.isdir(data_intel):
            os.makedirs(data_intel)

        if self.apk_file is not None:
            apkzip = zipfile.ZipFile(self.apk_file, 'r')
            for name in apkzip.namelist():
                if '.zip' in name:
                    apk_cache = os.path.join(self.build_dir, '.apkcache')
                    if not os.path.isdir(apk_cache):
                        os.makedirs(apk_cache)
                    amplxeandroidzip = os.path.join(apk_cache, os.path.basename(name))
                    self._extract_from_zip(name, amplxeandroidzip, apkzip)
                    amplxezip = zipfile.ZipFile(amplxeandroidzip, 'r')
                    for amplxe_name in amplxezip.namelist():
                        if 'ittnotify' in amplxe_name:
                            apk_itt = os.path.join(apk_cache, os.path.basename(amplxe_name))
                            self._extract_from_zip(amplxe_name, apk_itt, amplxezip)
                            shutil.copy(apk_itt, dst_ittnotify)
                    amplxezip.close()
                    shutil.rmtree(apk_cache, True)
            apkzip.close()
        else:
            shutil.copy(src_ittnotify, dst_ittnotify)

    def _extract_from_zip(self, name, dest_path, zip_file):
        dest_file = open(dest_path, 'wb')
        dest_file.write(zip_file.read(name))
        dest_file.close()

    def _create_tmp_dir(self):
        product_tmp_dir = self.build_dir + self.product.get_tmp_dir()
        os.makedirs(product_tmp_dir)
        open(os.path.join(product_tmp_dir, ".keepme"), "w")

    def _create_results_dir(self):
        product_prj_dir = os.path.join(self.build_dir, "data/amplxe/results")
        os.makedirs(product_prj_dir)
        open(os.path.join(product_prj_dir, ".keepme"), "w")

    def _copy_bin32_dir(self):
        src_bin32 = os.path.join(self.pkg_root_dir,  "bin32")
        dst_bin32 = os.path.join(self.install_dir, "bin32")
        shutil.copytree(src_bin32, dst_bin32)

    def _copy_lib32_dir(self):
        src_lib32 = os.path.join(self.pkg_root_dir,  "lib32")
        dst_lib32 = os.path.join(self.install_dir, "lib32")
        shutil.copytree(src_lib32, dst_lib32)
        shutil.rmtree(os.path.join(dst_lib32, "python"), True)
        for lib in glob.glob(os.path.join(dst_lib32, "*.a")):
            os.remove(lib)

    def _copy_message_dir(self):
        src_message = os.path.join(self.pkg_root_dir,  "message")
        dst_message = os.path.join(self.install_dir, "message")
        shutil.copytree(src_message, dst_message)

    def _copy_config(self):
        src_doc = os.path.join(self.pkg_root_dir, "config")
        if os.path.isdir(src_doc):
            dst_doc = os.path.join(self.install_dir, "config")
            shutil.copytree(src_doc, dst_doc)

    def _copy_doc_dir(self):
        for doc in ['doc', 'documentation']:
            src_doc = os.path.join(self.pkg_root_dir, doc)
            if os.path.isdir(src_doc):
                dst_doc = os.path.join(self.install_dir, "doc")
                shutil.copytree(src_doc, dst_doc)
                break

    def _check_adb(self):
        if not self.adb.is_ready():
            self.options.messenger.write("adb cannot communicate with a device.\n")
            sys.exit(1)

        if self.adb.get_arch() is None:
            self.options.messenger.write("Unsupported device architecture - %s.\n" % self.adb.get_arch())
            sys.exit(1)

    def _check_adb_root(self):
        if not self.adb.is_root():
            self.options.messenger.write("device isn't in root mode.\n")
            sys.exit(1)

class RunTool:
    def __init__(self, shell, product, options):
        self.options = options
        self.result_dir = None
        self.target_pid = None
        self.useDrivers = False

        if options.option_file:
            self.result_dir = self._get_option_value_from_option_file(options.option_file,  ["-r", "--result-dir"])
            self.target_pid = self._get_option_value_from_option_file(options.option_file,  ["--target-pid"])
            if self.target_pid:
                self.target_pid = int(self.target_pid)
                self.options.target_pid = self.target_pid
            self.target_process = self._get_option_value_from_option_file(options.option_file,  ["--target-process"])
            self.options.target_process = self.target_process
            command = self._get_option_value_from_option_file(options.option_file,  ["-C", "--command"])
            if command != None:
                options.command = command

            if self._get_option_value_from_option_file(options.option_file,  ["--event-config"]) is not None:
                self.useDrivers = True
        else:
            if '--context-value-list' in options.runss_args or '--event-config' in options.runss_args:
                self.useDrivers = True


        if self.result_dir is None:
            self.result_dir = options.result_dir

        self.shell = shell
        self.product = product
        self.mic = options.mic

        create_result_dir = '--context-value-list' not in options.runss_args

        # Create <result_dir> directory if it doesn't exist
        if not os.path.exists(self.result_dir) and create_result_dir:
            os.makedirs(self.result_dir)

        # Create <result_dir>/log directory if it doesn't exist
        log_dir = options.log_folder or os.path.join(self.result_dir, "log", "target")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_name = os.path.join(log_dir, "amplxe_runss.py.%s.log" % os.getpid())
        self.host_log_dir = log_dir

        self.options.log_name = log_name
        logging.basicConfig(filename=self.options.log_name, level=logging.DEBUG)
        if options.verbose:
            console = logging.StreamHandler()
            console.setLevel(logging.INFO)
            formatter = logging.Formatter("%(levelname)-8s %(message)s")
            console.setFormatter(formatter)
            logging.getLogger('').addHandler(console)

        if not self.shell.is_ready():
            self.options.messenger.write("Cannot communicate with target.\n")
            sys.exit(8)

        if self.product.get_layout_name() == 'android' and self.shell.is_root():
            cat_output = self.shell.cat('/data/local.prop')
            logging.debug("/data/local.prop options: %s", cat_output)

        remote_cfg = self.result_dir + '/config/remote.cfg'
        self.remote_dir = self._get_option_value_from_option_file(remote_cfg, ['--result-dir'])
        self.tmp_log_dir_name = ''
        if self.remote_dir == None:
            tmp_name = os.path.basename(tempfile.NamedTemporaryFile().name)
            self.tmp_log_dir_name = tmp_name
            tmp_name = self.options.target.replace('@', '_') + '/' + tmp_name + '/' + os.path.basename(self.result_dir)
            self.remote_dir = self.product.get_project_dir() + tmp_name
            try:
                if os.path.exists(self.result_dir):
                    config_dir = os.path.join(self.result_dir, "config")
                    if not os.path.exists(config_dir):
                        os.makedirs(config_dir)
                    open(remote_cfg, "w").write('--result-dir\n' + self.remote_dir + '\n')
            except:
                pass
        else:
            self.tmp_log_dir_name = os.path.basename(os.path.dirname(self.remote_dir))

        if not options.module_dir:
            self.module_dir = os.path.join(self.result_dir, 'all')
        else:
            self.module_dir = options.module_dir
        self.arch = self.shell.uname("-m")

        # Create <result_dir>/all directory if it doesn't exist
        if not os.path.exists(self.module_dir) and create_result_dir:
            os.makedirs(self.module_dir)

        self.tmp_dir = self.product.get_tmp_dir()
        self.runss_args = ["--result-dir", self.remote_dir, "--tmp-dir", os.path.join(self.tmp_dir, self.tmp_log_dir_name)]
        self.runss_args += options.runss_args
        self.search_dirs = []
        self.option_file = options.option_file

        self.options = options

        if self._is_ebs_collection() or self.mic:
            if options.pmu_stack:
                self.runss_args += ["--collector", "vtsspp"]
            else:
                self.runss_args += ["--collector", "sep"]
        if not self.mic and '--ptrace' in options.runss_args:
            if options.ptrace_stack:
                self.runss_args += ["--stack"]
            else:
                self.runss_args += ["--no-stack"]

        if '--context-value-list' not in options.runss_args:
            self.runss_args += ["--compression=0"]

        self._set_search_dirs()

        logging.debug("initializing RunTool class")
        logging.debug("result directory: %s", self.result_dir)
        logging.debug("extra arguments for runss: %s", self.runss_args)
        logging.debug("option file: %s", self.option_file)

    def run(self):
        self._insmod_drivers()
        retcode = self._call_runtool(self.runss_args)
        self._rmmod_drivers()
        return retcode

    def start(self, args):
        logging.debug("start data collection: %s", args)
        return self._collect_data(args)

    def attach(self, identifier):
        logging.debug("attach to %s process", identifier)
        if isinstance(identifier, int):
            self.target_pid = identifier
            return self._collect_data(["--target-pid", str(identifier)])
        elif self.product.get_layout_name() == 'android':
            ps_output = self.shell.ps()
            logging.debug("ps output: %s", ps_output)
            target_pids = []
            for line in ps_output:
                if identifier == line.split()[-1]:
                    target_pids.append(line.split()[1])
            if len(target_pids) < 1:
                self.options.messenger.write("there are no processes for %s\n" % identifier)
                sys.exit(1)
            if len(target_pids) > 1:
                self.options.messenger.write("there are more than one processes for %s\n" % identifier)
                logging.debug("multiple attach - %s\n" % str(target_pids))
                sys.exit(1)
            if len(target_pids) > 0:
                self.target_pid = target_pids[0]
            logging.debug("target pid: %s", self.target_pid)
            return self._collect_data(["--target-pid", str(self.target_pid)])
        else:
            return self._collect_data(["--target-process", identifier])

    def mark(self):
        return self.execute("mark")

    def cancel(self):
        return self.execute("cancel")

    def pause(self):
        return self.execute("pause")

    def resume(self):
        return self.execute("resume")

    def detach(self):
        return self.execute("detach")

    def stop(self):
        return self.execute("stop")

    def execute(self, command):
        return self._call_runtool(self.runss_args + ['-C', command])

    def _set_search_dirs(self):
        self.search_dirs = []

        directories = self.options.search_dir
        if directories:
            self.search_dirs += directories

        if self.options.option_file:
            option_file_directories = self._get_option_values_from_option_file(self.options.option_file,  ["--search-dir"])
            if option_file_directories:
                #remove special symbols from path.
                #all:r=path --> path
                option_file_directories = map(lambda x: x if x.find("=")==-1 else x.partition("=")[2], option_file_directories)
                self.search_dirs += option_file_directories

        logging.debug("set search directories: %s", self.search_dirs)

    def _get_option_value_from_option_file(self, path, option_keys):
        return self._get_option_values_from_option_file(path, option_keys, True)

    def _get_option_values_from_option_file(self, path, option_keys, first_only = False):
        if path != None and os.path.exists(path):
            f = open(path, 'r')
        else:
            return None
        values = []
        for line in f:
            one_line = line.strip().split('=')
            if len(one_line) > 1:
                if one_line[0].strip() in option_keys:
                    if first_only:
                        return " ".join(one_line[1:])
                    else:
                        values.append(" ".join(one_line[1:]))
            else:
                if line.strip() in option_keys:
                    if first_only:
                        return f.next().strip()
                    else:
                        values.append(f.next().strip())

        if len(values) > 0:
            return values

        return None

    def _check_product(self):
        if self.product.get_layout_name() == 'android':
            output = " ".join(self.shell.get_cmd_output([self._get_runss_path(), '-V']))
            install_product = False
            if 'not found' in output:
                self.options.messenger.write("Could not find product on device. Automatic installation...\n", "info")
                logging.info("Could not find product on device. Automatic installation...")
                install_product = True
            else:
                m = re.match(".*build\s+(?P<version>\d+)", output)
                if m:
                    current_version = None
                    version = int(m.group('version'))

                    support_file = None
                    script_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
                    support_file_dirs = [
                                        os.path.join(script_dir, '..'),
                                        os.path.join(script_dir, '..', '..'),
                                    ]
                    for support_file_dir in support_file_dirs:
                        support_file_tmp = os.path.join(support_file_dir, 'support.txt')
                        if os.path.isfile(support_file_tmp):
                            support_file = support_file_tmp
                            break
                    if support_file != None:
                        for line in open(support_file, 'r').readlines():
                            m = re.match(".*Build\s+Number:\s+(?P<version>\d+)", line.strip())
                            if m:
                                current_version = int(m.group('version'))
                                break
                    if current_version != None and current_version > version:
                        self.options.messenger.write("Need to update package on device. Automatic update...\n", "info")
                        logging.info("Need to update package on device. Automatic update...")
                        install_product = True

            #lazy installation of product
            if install_product:
                installer = AndroidPackageInstaller(self.options)
                installer.clean()
                installer.install()
        else:
            if 'No such file' in str(self.shell.ls(self._get_runss_path())):
                self.options.messenger.write("Could not find product on device. Check installation\n")
                sys.exit(1)

    def _collect_data(self, args):

        #check that product is exist and valid
        self._check_product()

        self.runss_args += args
        # Create <result_dir>/config/runss.options
        self.options.remote_option_file = ""
        if self.option_file:
            #python subprocess.Popen could not run too long cmd. So, stay options file copying
            #try:
            #    f = open(self.option_file, 'r')
            #    for line in f:
            #        self.runss_args += [line.strip()]
            #except:
            remote_file = self.product.get_tmp_dir() + self.options.target + '_' + os.path.basename(self.remote_dir) +  '_runss.options'
            self.shell.push(self.option_file, remote_file)
            self.runss_args += ["--option-file", remote_file]
            self.options.remote_option_file = remote_file
        elif '--context-value-list' not in self.options.runss_args:
            self._create_option_file(self.runss_args)

        # We need to do here extra insmod/rmmod to avoid problems with NMI
        # driver. By some reason it can be enabled and rmmod/insmod here is
        # an extra delay.
        # TODO: investigate how to avoid the problem completely. Probably
        # we should print a warning if NMI watchdog timer is enabled.
        if self.mic:
            if not self._create_context_cfg():
                self.options.messenger.write("could not create context cfg\n")
                sys.exit(1)
            retcode = self._call_runtool(self.runss_args)
        else:
            if not self.shell.is_root() and (self._is_ebs_collection() or self._is_pwr_collection()):
                self.options.messenger.write("this collection type could not be started.\n")
                self.options.messenger.write("Device is not in root mode\n")
                sys.exit(1)
            if not self.shell.is_root() and ('--ptrace' in self.runss_args or self._get_option_value_from_option_file(self.options.option_file,  ["--ptrace"]) == 'cpu') and self.target_pid:
                package_name = self.shell.cat("/proc/" + self.target_pid + "/cmdline")
                package_name = str(package_name[0]).split('\x00')[0]
                runas_id_output = self.shell.get_cmd_output(["run-as", package_name, "id"])[0]
                if ('is unknown' in runas_id_output):
                    self.options.messenger.write("target package can not be found on your device.\n")
                    self.options.messenger.write(runas_id_output)
                    sys.exit(1)
                if ('is not debuggable' in runas_id_output):
                    self.options.messenger.write("target application can not be profiled without debug flag.\n")
                    self.options.messenger.write("Please, set debug flag 'android:debuggable'.\nhttp://developer.android.com/guide/topics/manifest/application-element.html\n")
                    self.options.messenger.write("Application is not debuggable\n")
                    sys.exit(1)
            if ('--ptrace' not in self.runss_args and self.shell.is_root()):
                self._insmod_drivers()
                if not self._create_context_cfg():
                    self._rmmod_drivers()
                    self.options.messenger.write("could not create context cfg\n")
                    sys.exit(1)
                retcode = self._call_runtool(self.runss_args)
                self._rmmod_drivers()
            else:
                retcode = self._call_runtool(self.runss_args)
        if retcode == 0 or retcode == 4: #4 need for duration detach
            if ('--event-list' not in self.runss_args) \
                and ('--context-value-list' not in self.runss_args):
                self._copy_results()
                self._copy_modules()
        self._copy_logs()
        return retcode

    def _copy_results(self):
        if self.options.option_file:
            processbar = EmptyProgressBar("")
            self.options.messenger.write(message = "Copying results dir from the device\n", severity = "info")
        else:
            processbar = ProgressBar("Copying results from the device:")
        processbar.start()
        self.shell.rpull(self.remote_dir, self.result_dir)
        self.shell.rm("-r", self.remote_dir, self.options.remote_option_file)
        result_data_dir = os.path.join(self.result_dir, "data.0")
        if self.target_pid:
            jit_pattern = re.compile("localhost\.%s(-[0-9]+)?\.jit" % self.target_pid)
            project_dir = "/data/amplxe/results/"
            ls_output = self.shell.ls(project_dir)
            logging.debug("list of jit files: %s", ls_output)
            for filename in ls_output:
                if jit_pattern.search(filename):
                    self.shell.pull(project_dir + filename, result_data_dir)
        processbar.stop()

    def _copy_logs(self):
        if self.options.option_file:
            processbar = EmptyProgressBar("")
            self.options.messenger.write(message = "Copying collection logs from the device\n", severity = "info")
        else:
            processbar = ProgressBar("Copying collection logs from the device:")
        processbar.start()
        if os.path.exists(self.result_dir):
            dst_log_dir = os.path.join(self.result_dir, "log", "target")
        else:
            dst_log_dir =  self.host_log_dir

        if not os.path.exists(dst_log_dir):
            os.makedirs(dst_log_dir)

        src_log_dir = os.path.join(self.tmp_dir, self.tmp_log_dir_name)
        self.shell.rpull(src_log_dir, dst_log_dir)
        self.shell.rm("-r", src_log_dir, os.path.dirname(src_log_dir) + '/amplxe-log-*')

        if os.path.exists(os.path.join(dst_log_dir, "[vdso]")):
            os.remove(os.path.join(dst_log_dir, "[vdso]"))

        processbar.stop()

    def _copy_modules(self):
        if self.options.no_copy_modules:
            return

        if self.options.option_file:
            processbar = EmptyProgressBar("")
            self.options.messenger.write(message = "Copying modules from the device\n", severity = "info")
        else:
            processbar = ProgressBar("Copying modules from the device:")
        processbar.start()
        result_data_dir = os.path.join(self.result_dir, "data.0")
        tracefiles  = glob.glob(os.path.join(result_data_dir, "*.tb6"))
        tracefiles += glob.glob(os.path.join(result_data_dir, "*.vtss"))
        tracefiles += glob.glob(os.path.join(result_data_dir, "*.vtss.aux"))
        tracefiles += glob.glob(os.path.join(result_data_dir, "*.pwr"))
        tracefiles += glob.glob(os.path.join(result_data_dir, "*.pt"))
        tracefiles += glob.glob(os.path.join(result_data_dir, "*.trace"))
        logging.debug("list of trace files: %s", tracefiles)

        cache_dir = self._prepare_cache_dir()

        if self.product.get_layout_name() == 'android':
            # FIXME: /lib/modules/*.ko it is specific of Android platform
            ls_output = self.shell.ls("/lib/modules/*.ko")
            logging.debug("list of kernel modules: %s", ls_output)
            for remote_path in ls_output:
                local_path = self._pull_module(remote_path, cache_dir)
                if os.path.isfile(local_path):
                    logging.debug("copy %s to %s", local_path, self.module_dir)
                    shutil.copy(local_path, self.module_dir)

        re_sysmodule = self.product.get_sysmodule_pattern()
        re_axemodule = re.compile(self.product.get_install_dir())

        # It is optimization. Look at '/' directory and construct the following
        # pattern: vmlinux|^/dir1|^/dir2... It will filter out most of all
        # trash.
        ls_output = self.shell.ls("/")
        logging.debug("list of directories/files from '/': %s", ls_output)
        escaped_list = ["vmlinux"] + [re.escape(x) for x in ls_output]
        module_pattern = "|^/".join(escaped_list)
        logging.debug("pattern for modules: %s", module_pattern)
        re_anymodule = re.compile(module_pattern)

        strings = set()
        for tracefile in tracefiles:
            strings.update(RunTool._extract_strings(tracefile))

        logging.debug("Unfiltered strings from tracefiles: %s", strings)
        strings = filter(re_anymodule.match, strings)
        logging.debug("Filtered strings from tracefiles: %s", strings)
        for remote_path in strings:
            if re_axemodule.match(remote_path):
                logging.warning("skip %s module from AXE package", remote_path)
                continue
            if remote_path.startswith("/dev/"):
                logging.warning("skip %s module from /dev/", remote_path)
                continue

            #if remore_path.startswith("/dev/"):
            #    logging.warning("skip %s pseudo file from /dev/", remote_path)
            #    continue

            # Several modules with the same name but with different pathes can
            # be in one process. Thus we can't use flat directory layout for
            # <result-dir>/all directory.
            remote_dir = os.path.dirname(remote_path)
            module_dir = os.path.join(self.module_dir, remote_dir[1:])

            if not os.path.exists(module_dir):
                os.makedirs(module_dir)

            # First try to find the module on local filesystem. Don't try to
            # cache the result. Module cache directory should contain only
            # modules from the device.
            local_path = self._search_file(remote_path)
            if local_path:
                logging.debug("copy %s to %s", local_path, module_dir)
                shutil.copy(local_path, module_dir)
            elif re_sysmodule.match(remote_path):
                local_path = self._pull_module(remote_path, cache_dir)
                if os.path.isfile(local_path):
                    logging.debug("copy %s to %s", local_path, module_dir)
                    shutil.copy(local_path, module_dir)
            else:
                self._pull_module(remote_path, self.module_dir)

            for ext in ['.dbg', '.pdb']:
                # Try to find separate debug file on local filesystem. Don't try
                # to cache the result. The idea is very useful for Android. For
                # example, some graphics libraries have such files.
                debug_file = remote_path.split('.so')[0] + ext
                local_path = self._search_file(debug_file)
                if local_path:
                    logging.debug("copy %s to %s", local_path, module_dir)
                    shutil.copy(local_path, module_dir)
        processbar.stop()

    def _search_file(self, remote_path):
        search_dirs = self.search_dirs
        if self.mic:
            search_dirs += ["/opt/intel/mic/filesystem/base", "/lib/firmware/mic"]
        for dir in search_dirs:
            file_path = os.path.join(dir, remote_path[1:])
            if os.path.isfile(file_path):
                return file_path
            file_path = os.path.join(dir, os.path.basename(remote_path))
            if os.path.isfile(file_path):
                return file_path

        return None

    def _pull_module(self, remote_path, local_dir):
        local_path = os.path.join(local_dir, remote_path[1:])

        if not os.path.exists(local_path):
            directory = os.path.dirname(local_path)
            if not os.path.exists(directory):
                os.makedirs(directory)
            self.shell.pull(remote_path, local_path)

        return local_path

    @staticmethod
    def _extract_strings(filepath):
        file = open(filepath, "rb")
        content = file.read(64*1024*1024)
        strings = []
        while content:
            strings += re.findall(b("([\x20-\x7e]{4,})[\n\0]"), content)
            # Don't lose strings between chunks. Here I believe that strings cannot be
            # more than 4096 bytes. It is possible that we will add an extra substring.
            # It isn't important.
            content = content[-4096:] + file.read(64*1024*1024)
            if len(content) <= 4096: break
        return [decode(x) for x in strings if x]

    def _prepare_cache_dir(self):
        uname_output = self.shell.uname("-a")
        serialno = self.shell.serialno()
        serialno = serialno.replace(':', '_')
        cache_dir = os.path.join(tempfile.gettempdir(), "amplxe-runss.db.%s.%s"
            % (getpass.getuser(), serialno))
        uname_filepath = os.path.join(cache_dir, 'dev_uname.info.txt')

        if os.path.exists(cache_dir):
            logging.debug("%s cache directory exists", cache_dir)
            if open(uname_filepath).read() != uname_output:
                logging.debug("delete obsolete cache directory")
                shutil.rmtree(cache_dir, True)

        if not os.path.exists(cache_dir):
            logging.debug("create %s cache directory", cache_dir)
            logging.debug("uname -a for the device: %s", uname_output)
            os.makedirs(cache_dir)
            open(uname_filepath, "w").write(uname_output)

        return cache_dir

    def _get_runss_path(self):
        if self.product.get_layout_name() == 'android':
            runss_path = self.product.get_binary_path("runss.sh", self.arch)
        # If 'runss.sh' helper script doesn't exist we use 'runss' binary.
        else:
            runss_path = self.product.get_binary_path("runss", self.arch)
        return runss_path

    def _call_runtool(self, args, **kwargs):
        runss_path = self._get_runss_path()

        log_dir = os.path.join(self.tmp_dir, self.tmp_log_dir_name)
        if self.shell.is_root():
            # Some programs are trying to write into the current directory. Thus
            # to avoid any problems with pemissions we "cd" into "tmp" directory.
            return self.shell.call(["cd", self.tmp_dir, ";", "mkdir", "-p", log_dir, ";", 'AMPLXE_LOG_DIR=' + log_dir, runss_path] +  args, **kwargs)
        else:
            # on not-rooted devices we could not cd to tmp and set BIN_DIR
            return self.shell.call(["mkdir", "-p", log_dir, ";", 'AMPLXE_LOG_DIR=' + log_dir, runss_path] +  args, **kwargs)

    def _exists(self, path):
        return self.shell.call(["ls"] + [path], silent=True) == 0

    def _find_driver(self, name):
        drv_paths = [
                        self.product.get_driver_path(name, self.arch),
                        '/lib/modules/%s.ko' % name,
                        '/system/lib/modules/%s.ko' % name
                    ]
        for drv_path in drv_paths:
            if self._exists(drv_path):
                return drv_path
        return None

    def _insmod_drivers(self):
        if self.product.get_layout_name() != 'android' or not self.shell.is_root() or not self.useDrivers:
            return

        self.loaded_drivers = []

        drivers_aliases = {
                              "pax"    : "pax",
                              "sep"    : os.getenv('SEP_VERSION', "sep3_10"),
                              "vtsspp" : "vtsspp",
                          }

        drivers_set = sum([[drivers_aliases[x]] for x in drivers_aliases.keys()], [])
        drivers = sum([[self._find_driver(x)] for x in drivers_set], [])
        drivers = sum([[x] for x in drivers if x], [])
        logging.debug("drivers on target device - " + str(drivers))
        command = sum([["insmod", x, ";"] for x in drivers if x], [])

        if not command:
            return

        logging.debug("call insmod command \"" + " ".join(command) + "\"")
        self.loaded_drivers = sum([[os.path.splitext(os.path.basename(x))[0]] for x in drivers if x], [])
        if self.shell.call(command) != 0:
            self._rmmod_drivers(silent=True)
            if self.shell.call(command) != 0:
                self.options.messenger.write(" could not execute \'insmod\' command for drivers - " + " ".join(drivers) + "\n")
                sys.exit(1)

        missed_drivers = set(drivers_set) ^ set(self.loaded_drivers)
        if not len(missed_drivers):
            return

        if '--context-value-list' in self.options.runss_args: #don't need to check - context-value-list command verifies itself
            return

        failedCollection = False
        if self._is_pwr_collection() and drivers_aliases["pwr"] in missed_drivers:
            self.options.messenger.write("could not execute power collection - " + drivers_aliases["pwr"] + " driver is missed on target.\n")
            failedCollection = True
        elif self._is_ebs_collection():
            if drivers_aliases["pax"] in missed_drivers or drivers_aliases["sep"] in missed_drivers:
                self.options.messenger.write("could not execute collection - " + drivers_aliases["sep"] + " and/or " + drivers_aliases["pax"] + " drivers are missed on target.\n")
                another_valid_sep = {'sep3_8':'sep3_10', 'sep3_10':'sep3_8'}[drivers_aliases["sep"]]
                if self._find_driver(another_valid_sep) is not None:
                    self.options.messenger.write("This is " + drivers_aliases["sep"] + ' VTune Amplifier 2013 for Android package')
                    self.options.messenger.write(" but " + another_valid_sep + " is located on system only.\n")
                    self.options.messenger.write("Are you sure that VTune Amplifier 2013 for Android package is correct?\n")

                failedCollection = True
            elif self.options.pmu_stack and drivers_aliases["vtsspp"] in missed_drivers:
                self.options.messenger.write("could not execute collection - " + drivers_aliases["vtsspp"] + " driver is missed on target\n")
                failedCollection = True
        if failedCollection:
            self._rmmod_drivers()
            sys.exit(1)

        logging.debug(str(list(missed_drivers)) + " could not be found on target device")

    def _rmmod_drivers(self, silent = False):
        if self.product.get_layout_name() != 'android' or not self.shell.is_root() or not self.useDrivers:
            return

        if self.loaded_drivers:
            command = sum([["rmmod", x, ";"] for x in self.loaded_drivers], [])
            status = self.shell.call(command)

            if silent:
                return

            if status != 0:
                self.options.messenger.write("could not execute \'rmmod\' command for drivers - " + " ".join(self.loaded_drivers) + "\n")
                sys.exit(1)
            self.loaded_drivers = []

    def _is_ebs_collection(self):
        a = "--pmu-config"   in self.runss_args
        b = "--event-config" in self.runss_args
        return a or b

    def _is_pwr_collection(self):
        return "--pwr-config" in self.runss_args

    def _is_itt_collection(self):
        return "--itt-config" in self.runss_args

    def _create_option_file(self, runss_args):
        config_dir = os.path.join(self.result_dir, "config")
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        option_file = os.path.join(config_dir, 'runss.options')
        for argument in runss_args:
            open(option_file, "a").write(argument + '\n')

    def _create_context_cfg(self):
        if '--context-value-list' in self.options.runss_args or self.options.option_file:
            return True

        config_dir = os.path.join(self.result_dir, "config")
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        runss_path = self._get_runss_path()
        self.ctx_value_list = self.shell.get_cmd_output(
            ['BIN_DIR=' + os.path.dirname(runss_path), runss_path, "--context-value-list"])
        logging.debug("context value list: %s", self.ctx_value_list)

        ctx_values_cfg = os.path.join(config_dir, 'context_values.cfg')
        if not os.path.exists(ctx_values_cfg):
            xml_file = '''<?xml version="1.0" encoding="UTF-8"?>
<bag xmlns:boolean="http://www.w3.org/2001/XMLSchema#boolean"
    xmlns:double="http://www.intel.com/2001/XMLSchema#double"
    xmlns:int="http://www.w3.org/2001/XMLSchema#int"
    xmlns:unsignedInt="http://www.w3.org/2001/XMLSchema#unsignedInt">
'''
            try:
                for line in self.ctx_value_list:
                    (key, value) = line.split(":")
                    value = value.strip()
                    if self.mic and key == "PMU":
                        xml_file += '''
    <contextValue id="PMU" value="knc"/>'''
                    elif value == "true" or value == "false":
                        xml_file += """
    <contextValue id=\"%s\" boolean:value=\"%s\"/>""" % (key, value)
                    else:
                        xml_file += """
    <contextValue id=\"%s\" value=\"%s\"/>""" % (key, value)

                if self.product.get_layout_name() == 'android':
                    xml_file += '''
    <contextValue id="OS" value="Android"/>
    <contextValue id="pmuEventConfig" value="CPU_CLK_UNHALTED.REF:,INST_RETIRED.ANY:"/>'''
                else:
                    xml_file += '''
    <contextValue id="OS" value="Linux"/>
    <contextValue id="pmuEventConfig" value="CPU_CLK_UNHALTED:,INSTRUCTIONS_EXECUTED:"/>'''
                xml_file += '''
    <contextValue id="CLIENT_ID" value="CLI"/>
    <contextValue id="allowMultipleRuns" boolean:value="false"/>
    <contextValue id="analyzeSystemWide" boolean:value="false"/>
    <contextValue id="basicBlockAnalysis" boolean:value="true"/>
    <contextValue id="collectCallCounts" boolean:value="false"/>
    <contextValue id="collectMemBandwidth" boolean:value="false"/>
    <contextValue id="collectUserTasksMode" boolean:value="false"/>
    <contextValue id="cpuMask" value=""/>
    <contextValue id="dataLimit" int:value="100"/>
    <contextValue id="enableCallCountCollection" boolean:value="false"/>
    <contextValue id="enableLBRCollection" boolean:value="false"/>
    <contextValue id="enablePEBSCollection" boolean:value="false"/>
    <contextValue id="enableStackCollection" boolean:value="true"/>
    <contextValue id="enableVTSSCollection" boolean:value="true"/>
    <contextValue id="followChild" boolean:value="true"/>
    <contextValue id="followChildStrategy" value=""/>
    <contextValue id="goodFastFrameThreshold" double:value="100"/>
    <contextValue id="gpuCounters" value="off"/>
    <contextValue id="gpuCountersCollection" value=""/>
    <contextValue id="initialReport" value="summary"/>
    <contextValue id="initialViewpoint" value="%LightweightHotspotsViewpointName"/>
    <contextValue id="isGPUAnalysisAvailable" boolean:value="false"/>
    <contextValue id="mrteMode" value="auto"/>
    <contextValue id="runsa:enable" boolean:value="true"/>
    <contextValue id="slowGoodFrameThreshold" double:value="40"/>
    <contextValue id="targetDurationType" value="short"/>
    <contextValue id="targetType" value="launch"/>
    <contextValue id="useCountingMode" boolean:value="false"/>
    <contextValue id="useEventBasedCounts" boolean:value="false"/>
    <contextValue id="userTasksCollection" boolean:value="false"/>
</bag>'''
                open(ctx_values_cfg, 'w').write(xml_file)
            except:
                return False
        return True

def which(program): #same as Linux which command - finds full path to given executable
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
        if sys.platform == 'win32' and is_exe(program + ".exe"):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
            if sys.platform == 'win32' and is_exe(exe_file + ".exe"):
                return exe_file
    return None

def get_last_result_dir(pattern):
    directory = pattern.replace("@", "[0-9]")
    result_dirs = sorted(glob.glob(directory))
    if result_dirs:
        return os.path.abspath(result_dirs[-1])
    else:
        return None

def get_next_result_dir(pattern):
    directory = get_last_result_dir(pattern)
    if directory:
        directory = directory[-len(pattern):]
        result_dir = []
        is_done = False
        for (x, y) in zip(reversed(pattern), reversed(directory)):
            if not is_done and x == "@":
                if y == "9":
                    result_dir.append("0")
                else:
                    result_dir.append(str(int(y) + 1))
                    is_done = True
            else:
                result_dir.append(y)
        result_dir.reverse()
        result_dir = "".join(result_dir)
    else:
        result_dir = pattern.replace("@", "0")

    return os.path.abspath(result_dir)

def add_search_dir(option, opt, value, parser):
    if not parser.values.search_dir:
        parser.values.search_dir = []
    parser.values.search_dir += value.split(",")

def add_runss_args(option, opt, value, parser):
    if not parser.values.runss_args:
        parser.values.runss_args = []
    parser.values.runss_args += [opt]
    if value:
        parser.values.runss_args += [str(value)]


def main():
    package_installation = False
    #AMPLXE_INSTALL_DEVICE_PACKAGE will be set in installation wrapper to hide collection options
    #and amplxe-runss.py script will be look like installation script only
    if os.getenv('AMPLXE_INSTALL_DEVICE_PACKAGE', '0') == '1':
        package_installation = True
    if package_installation:
        parser = OptionParser(usage="Usage: amplxe-androidreg{.bat|.sh} --package-command=<install|uninstall|build> [--use-cache] [--with-drivers] [--jitvtuneinfo]")
    else:
        parser = OptionParser(usage = "Usage: %prog [options] [[--] <application> [<args>]]")

        collection_group = OptionGroup(parser, "Collection options")
        collection_group.add_option("-r", "--result-dir",
                          metavar="DIRECTORY",
                          default="r@@@",
                          dest="result_dir",
                          help="Specify the directory used for creating the data collection results.")

        collection_group.add_option("--target-process",
                          metavar="NAME",
                          dest="target_process",
                          help="Specify the name for the process to which data collection should be attached.")

        collection_group.add_option("--target", "--target-system",
                          metavar="host",
                          dest="target",
                          help="Specify target for data collection.")

        collection_group.add_option("--target-install-dir",
                          metavar="host",
                          dest="install_dir",
                          help="Specify target installation folder.")

        collection_group.add_option("--log-folder",
                          metavar="host",
                          dest="log_folder",
                          help="Specify host log folder.")

        collection_group.add_option("--target-pid",
                          metavar="PID",
                          type="int",
                          dest="target_pid",
                          help="Specify ID for the process to which data collection should be attached.")

        collection_group.add_option("-C", "--command",
                          type="choice",
                          choices=["pause", "resume", "detach", "stop", "mark", "cancel"],
                          help="Process control command for a given result directory. " +
                          "Possible commands: " +
                          "pause - pause profiling all processes for a given result directory; " +
                          "resume - resume profiling all processes for a given result directory; " +
                          "stop - stop data collection; " +
                          "mark - put a discrete mark into the data being collected; " +
                          "detach - detach from a given result directory.")

        collection_group.add_option("--no-modules",
                      action="store_true",
                      default=False,
                      dest="no_copy_modules",
                      help="Don't copy modules from target device.")

        collection_group.add_option("--module-dir",
                          metavar="DIRECTORY",
                          default="",
                          dest="module_dir",
                          help="Specify the directory used for copying modules from target device.")

        collection_group.add_option("--search-dir",
                          type="string",
                          metavar="DIRECTORY",
                          dest="search_dir",
                          action="callback",
                          callback=add_search_dir,
                          help="Specify list of host directories where to search modules.")

        collection_group.add_option("-v", "--verbose",
                          action="store_true",
                          default=False,
                          dest="verbose",
                          help="Print additional information.")

        collection_group.add_option("--option-file",
                          type="string",
                          metavar="FILE",
                          help="Specify the path to the option file as <string>. " +
                          "Options from the specified file are read and applied. If options given" +
                          " on the command line conflict with options given in the file, the " +
                          "command line options overwrite the conflicting options read from the " +
                          "file. To specify an option name and its value, use equal sign, like " +
                          "\"name=value\", or put the option name and the option value on " +
                          "separate lines.")

        collection_group.add_option("--pwr-config",
                          type="string",
                          dest="runss_args",
                          action="callback",
                          callback=add_runss_args,
                          metavar="CONFIG",
                          help="Specify types of power data to be collected. " +
                          "Possible values: " +
                          "sleep - C-state information; " +
                          "frequency - P-state information; " +
                          "ktimer - kernel-level call stack path used to schedule a timer causing a C-state break.")

        collection_group.add_option("--itt-config",
                          type="string",
                          dest="runss_args",
                          action="callback",
                          callback=add_runss_args,
                          metavar="CONFIG",
                          help="Specify a sub-set of ITT API to collect. " +
                          "Possible values: all, frame, event, mark, task.")

        collection_group.add_option("--start-paused",
                          dest="runss_args",
                          action="callback",
                          callback=add_runss_args,
                          help="Start data collection in 'paused' mode. To re-start the " +
                          "data collection, issue the resume command.")

        collection_group.add_option("--resume-after",
                          type="int",
                          dest="runss_args",
                          action="callback",
                          metavar="MILLISECONDS",
                          callback=add_runss_args,
                          help="Specify the delay in milliseconds as integer to delay " +
                          "the data collection while the application is executing.")

        collection_group.add_option("--data-limit",
                          type="int",
                          dest="runss_args",
                          action="callback",
                          metavar="MB",
                          callback=add_runss_args,
                          help="Limit amount of data collected with the given value (in MB).")

        collection_group.add_option("-d", "--duration",
                          type="int",
                          dest="runss_args",
                          action="callback",
                          metavar="SECONDS",
                          callback=add_runss_args,
                          help="Specify duration for the collection in seconds.")

        collection_group.add_option("-i", "--interval",
                          type="int",
                          dest="runss_args",
                          action="callback",
                          metavar="MILLISECONDS",
                          callback=add_runss_args,
                          help="Specify an interval of data collection (for example, " +
                          "sampling) in milliseconds.")

        collection_group.add_option("--bts-count",
                          type="int",
                          dest="runss_args",
                          action="callback",
                          metavar="NUMBER",
                          callback=add_runss_args,
                          help="Specify the number of BTS records collected after each " +
                          "sample or context switch.")

        collection_group.add_option("--pmu-config", "--event-config",
                          type="string",
                          dest="runss_args",
                          action="callback",
                          metavar="CONFIG",
                          callback=add_runss_args,
                          help="Perform data collection for the events.")

        collection_group.add_option("--event-list",
                          dest="runss_args",
                          action="callback",
                          callback=add_runss_args,
                          help="List events for which a sampling data collection can be " +
                          "performed on this platform.")

        collection_group.add_option("--context-value-list",
                          dest="runss_args",
                          action="callback",
                          callback=add_runss_args,
                          help="Display possible context values.")

        collection_group.add_option("--ui-output-format",
                          type="string",
                          dest="runss_args",
                          action="callback",
                          callback=add_runss_args,
                          help="Output format.")

        collection_group.add_option("--event-mux",
                          dest="runss_args",
                          action="callback",
                          callback=add_runss_args,
                          help="Enable timer- or trigger-based event multiplexing.")

        collection_group.add_option("--pmu-stack",
                          action="store_true",
                          default=True,
                          dest="pmu_stack",
                          help="Enable collection of stacks together with PMU samples.")

        collection_group.add_option("--no-pmu-stack",
                          action="store_false",
                          dest="pmu_stack",
                          help="Disable collection of stacks together with PMU samples.")

        collection_group.add_option("--sample-after-multiplier",
                          type="float",
                          dest="runss_args",
                          action="callback",
                          metavar="DOUBLE",
                          callback=add_runss_args,
                          help="Specify the sample after multiplier as <double>. " +
                          "This multiplier modifies the sample after value " +
                          "for all the events specified in --event-config " +
                          "option. The values can range from 0.1 to 100.0.")

        collection_group.add_option("--cpu-mask",
                          type="string",
                          dest="runss_args",
                          action="callback",
                          metavar="STRING",
                          callback=add_runss_args,
                          help="Specify which CPU(s) <string> to collect data on. " +
                          "For example, specify \"2-8,10,12-14\" to sample " +
                          "only CPUs 2 through 8, 10, and 12 through 14.")

        collection_group.add_option("--stdsrc-config",
                          type="string",
                          dest="runss_args",
                          action="callback",
                          metavar="STRING",
                          callback=add_runss_args,
                          help="Enable etw/ftrace collector. Possible values: cswitch, igfx")

        collection_group.add_option("--etw-config",
                          type="string",
                          dest="runss_args",
                          action="callback",
                          metavar="STRING",
                          callback=add_runss_args,
                          help="Enable etw collector.")

        collection_group.add_option("--ptrace",
                          type="string",
                          dest="runss_args",
                          action="callback",
                          metavar="STRING",
                          callback=add_runss_args,
                          help="Enable driver-less Hotspots data collection. Possible values: cpu.")

        collection_group.add_option("--stack",
                          action="store_true",
                          dest="ptrace_stack",
                          help="Enable capture of stacks during driver-less Hotspots data collection.")

        collection_group.add_option("--no-stack",
                          action="store_false",
                          dest="ptrace_stack",
                          help="Disable capture of stacks during driver-less Hotspots data collection.")

        collection_group.add_option("--profiling-signal",
                          type="int",
                          dest="runss_args",
                          action="callback",
                          metavar="SIGNUM",
                          callback=add_runss_args,
                          help="Specify a signal to be used for driver-less Hotspots data collection. Default is 38.")

        parser.add_option_group(collection_group)

    internal_group = OptionGroup(parser, "Internal options")
    internal_group.add_option("--get-android-devices",
                  action="store_true",
                  default=False,
                  dest="get_android_devices",
                  help="get list of devices. Avalable fro android target only.")

    install_group = OptionGroup(parser, "Package installation options")
    install_group.add_option("--package-command",
                      type="choice",
                      choices=['install', 'uninstall', 'build'],
                      dest="package_command",
                      default=None,
                      help="choose package installation command - " +
                      "install, uninstall or build. ")
    install_group.add_option("--with-drivers",
                      action="store_true",
                      default=False,
                      dest="build_drivers",
                      help="build drivers (if your image doesn't have VTSS++ & SEP 3.xx drivers)")
    install_group.add_option("--kernel-src-dir",
                      metavar="DIRECTORY",
                      default=os.environ.get("ANDROID_KERNEL_SRC_DIR", None),
                      dest="kernel_src_dir",
                      help="directory of the configured kernel source tree")
    install_group.add_option("--kernel-version",
                      action="store",
                      type="string",
                      default=os.environ.get("KERNEL_VERSION", "unknown"),
                      dest="kernel_version",
                      help="version string of kernel")
    install_group.add_option("--use-cache",
                      action="store_true",
                      default=False,
                      help="use <cache> directory after 'build' command")
    install_group.add_option("--jitvtuneinfo",
                      type="choice",
                      choices=["jit", "src", "dex", "none", None],
                      default=None,
                      help="information about java byte code and source code; " +
                      "possible values: jit, src, dex, none. ")

    if package_installation:
        parser.add_option_group(install_group)

    (options, arguments) = parser.parse_args()
    if len(sys.argv) == 1:
        sys.stdout.write(parser.get_usage())
        return 1

    #installation command
    if options.package_command:
        adb   = which("adb")
        if not adb:
            error_message = "adb was not found on host. Add it to PATH\n"
            sys.stderr.write(error_message)
            return 1

        package = AndroidPackageInstaller(options)

        if not options.use_cache and options.package_command != "uninstall":
            package.clean()

        if   options.package_command == "build"    : package.build()
        elif options.package_command == "uninstall": package.uninstall()
        elif options.package_command == "install"  : package.install()
        else:
            sys.stderr.write(parser.get_usage())
            return 2
        return 0

    if options.option_file:
        if not os.path.exists(options.option_file):
            parser.error("invalid file path was specified for --option-file option")

    else:
        #TODO: Pending for no checks arguments
        if arguments and (options.target_pid or options.target_process):
            parser.error("options --target-pid or --target-process cannot be specified together " \
                "with an application.")

        if options.target_pid and options.target_process:
            parser.error("options --target-pid or --target-process cannot be specified together.")

        if options.command and (options.target_pid or options.target_process or arguments):
            parser.error("it is impossible to start a collection and send a command at the same time.")

        if not options.command and not options.target_pid and not options.target_process \
            and not arguments and options.pmu_stack \
            and not '--pwr-config' in sys.argv \
            and not '--event-list' in sys.argv \
            and not '--context-value-list' in sys.argv \
            and not options.get_android_devices \
            and not options.runss_args is None  \
            and not "--etw-config" in options.runss_args:
            parser.error("it is impossible to start a collection with stacks for system wide collection. " \
                          "\nuse --no-pmu-stack option or set target.")

    if not options.command:
        options.result_dir = get_next_result_dir(options.result_dir)
        if os.path.exists(options.result_dir):
            parser.error("please specify non-existent result directory using -r option.")
    else:
        tmp_result_dir = get_last_result_dir(options.result_dir)
        if tmp_result_dir == None:
            parser.error("Cannot open the result directory %s. Please specify a valid path." % options.result_dir)
        else:
            options.result_dir = tmp_result_dir

    if not options.runss_args:
        options.runss_args = []

    if '--ui-output-format xml' in " ".join(options.runss_args):
        xml_output = True
        options.messenger = MessageWriter(xml=True)
    else:
        xml_output = False
        options.messenger = MessageWriter(xml=False)

    options.mic = False
    if options.target and not re.match('^android', options.target):
        options.target = re.sub('^ssh:', '', options.target)
        plink = which("plink")
        pscp  = which("pscp")
        ssh   = which("ssh")
        scp   = which("scp")
        if sys.platform == 'win32' and plink and pscp:
            shell = Putty(options)
        elif ssh and scp:
            shell = SSH(options)
        else:
            error_message = " is not in PATH\n"
            if plink and not pscp:
                error_message = "pscp (command-line SCP (secure copy) / SFTP client)" + error_message
            elif not plink and pscp:
                error_message = "plink (PuTTY link, command line network connection tool)" + error_message
            elif ssh and not scp:
                error_message = "scp (secure copy (remote file copy program))" + error_message
            elif not ssh and scp:
                error_message = "ssh (OpenSSH SSH client (remote login program)" + error_message
            else:
                error_message = "ssh/scp or plink/pscp tools are not available in PATH\n"
            options.messenger.write(error_message)
            return 1
        if re.match("^mic", options.target):
            options.mic = True
            product = MICProductLayout()
        else:
            product = LinuxProductLayout(options)
    else:
        if options.target:
            target = options.target.split(':')
            if len(target) > 1:
                os.putenv('ANDROID_SERIAL', ":".join(target[1:]))

        options.target = 'android'

        adb   = which("adb")
        if not adb:
            error_message = "adb was not found on host. Add it to PATH\n"
            options.messenger.write(error_message)
            return 1

        product = AndroidProductLayout()
        shell = ADB(options = options, status_dir = os.path.join(product.get_install_dir(), '..'))

        if options.get_android_devices:
            shell.get_devices(xml=xml_output)
            return 0

    if product.get_layout_name() == 'android':
        #replace --pmu-config as deprecated option
        if '--pmu-config' in options.runss_args:
            options.runss_args[options.runss_args.index('--pmu-config')] = "--event-config"
        if not options.option_file and not options.command:
            if not options.runss_args or \
                ("--event-config" not in options.runss_args and \
                "--pwr-config"    not in options.runss_args and \
                "--ptrace"        not in options.runss_args and \
                "--etw-config"    not in options.runss_args and \
                "--stdsrc-config" not in options.runss_args and \
                "--context-value-list" not in options.runss_args and \
                "--itt-config"    not in options.runss_args):
                options.runss_args += ["--event-config", "CPU_CLK_UNHALTED.REF,CPU_CLK_UNHALTED.CORE,INST_RETIRED.ANY"]


    try:
        runtool = RunTool(shell, product, options)

        return_code = 0

        try:
            if not options.command:
                if options.target_pid:
                    return_code = runtool.attach(options.target_pid)
                    if not xml_output:
                        sys.stdout.write("Attach return code is " + str(return_code) + "\n")
                elif options.target_process:
                    return_code = runtool.attach(options.target_process)
                    if not xml_output:
                        sys.stdout.write("Attach return code is " + str(return_code) + "\n")
                elif options.runss_args or '--no-pmu-stack' in sys.argv:
                    return_code = runtool.start(arguments)
                    if not xml_output:
                        sys.stdout.write("Collection return code is " + str(return_code) + "\n")
                elif options.mic:
                    return_code = runtool.start(arguments)
                    if not xml_output:
                        sys.stdout.write("Collection return code is " + str(return_code) + "\n")
                else:
                    parser.print_usage(sys.stderr)
                    return_code = -1
            else:
                return_code = runtool.execute(options.command)
                if not xml_output:
                    if return_code != 0:
                        sys.stdout.write("Hint: Probably collection is not running\n")
                    sys.stdout.write(options.command + " command return code is " + str(return_code) + "\n")
            return return_code
        except KeyboardInterrupt:
            return 1
    finally:
        options.messenger.finalize()

if __name__ == "__main__":
    return_code = main()
    sys.exit(return_code)
