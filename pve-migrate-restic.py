#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This is a python script for import/export proxmox vms"""

import argparse
import subprocess
import sys
import re
import os
import getpass


def parse_args():
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("-l", "--url", dest="url", type=str, help="url for vault", required=True)
    parent_parser.add_argument("-p", "--password", dest="password", type=str, help="password for restic", required=True)
    parent_parser.add_argument("-m", "--vmid", dest="vmid", type=str, help="vmid to operation", required=True)
    group_1 = parent_parser.add_mutually_exclusive_group(required=False)
    group_1.add_argument("-k", "--access-key", dest="access_key", type=str, help="restic access key",
                         required=False)
    group_1.add_argument("-K", "--ask-access-key", dest="ask_access_key", action='store_true',
                         help="Ask restic access key",
                         required=False)
    parent_parser.set_defaults(ask_access_key=False)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title="command", description="valid subcommands", help="additional help")
    subparsers.required = True

    parser_export = subparsers.add_parser("export", help="Export VM", parents=[parent_parser])
    parser_export.set_defaults(func=export_vm)

    parent_parser_import = argparse.ArgumentParser(add_help=False)
    parent_parser_import.add_argument("-r", "--storage", type=str, dest="storage", help="storage for new VM",
                                      required=True)

    parser_import = subparsers.add_parser("import", help="Import VM")

    import_subparsers = parser_import.add_subparsers(title="import types", description="valid import types",
                                                     help="additional help")
    import_subparsers.required = True

    import_lxc_parser = import_subparsers.add_parser("lxc", help="Import VM",
                                                     parents=[parent_parser, parent_parser_import])

    import_lxc_parser.set_defaults(func=import_lxc_vm)

    import_lxc_parser.add_argument("-t", "--template", type=str, dest="template", help="template for new VM",
                                   required=True)
    import_lxc_parser.add_argument("-n", "--hostname", type=str, dest="hostname", help="hostname for new VM",
                                   required=False)

    import_lxc_parser.add_argument("-s", "--size", type=str, dest="size", help="root size in GB for new VM",
                                   required=True)

    return parser.parse_args()


def run_command_live(args, env=None):
    os_env = os.environ.copy()
    run_env = os_env if env is None else {**os_env, **env}
    process = subprocess.Popen(args, shell=True, stdout=subprocess.PIPE, universal_newlines=True,
                               executable="/bin/bash", env=run_env)
    while process.poll() is None:
        line = process.stdout.readline()
        print(line.strip())
    stdout, stderr = process.communicate()
    return {
        "code": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def run_command(args, env=None):
    os_env = os.environ.copy()
    run_env = os_env if env is None else {**os_env, **env}

    process = subprocess.Popen(args, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, executable="/bin/bash",
                               env=run_env)
    stdout, stderr = process.communicate()
    return {
        "code": process.returncode,
        "stdout": stdout.decode('utf-8'),
        "stderr": stderr.decode('utf-8'),
    }


def find_vm_lxc(id: int):
    command = "pct list"
    data = run_command(command)
    if (data["code"]) != 0:
        return None
    for line in data["stdout"].splitlines():
        if line.startswith(str(id)):
            m = re.match("(\d+)\s+(\w+)\s+((\w+)\s+)?(\S+)", line)
            if m:
                _, status, _, lock, name = m.groups()
                info = dict(zip(("id", "status", "lock", "name"), (id, status, lock, name)))
                return info
    return None


def find_vm_kvm(id: int):
    return None


def get_vm_info(id: int):
    info = find_vm_lxc(id)
    if info is not None:
        info["type"] = "lxc"
    else:
        info = find_vm_kvm(id)
        if info is None:
            return None
        info["type"] = "kvm"
    return info


def get_env_cmd(url: str, password: str):
    return f" . env-load {url} {password}"


def get_lxc_dump_cmd(vmid: int, vmname: str, vmtype: str):
    return f"vzdump {vmid} --mode stop --stdout --compress zstd" \
           f" | ifne restic backup -v --stdin --stdin-filename {vmname}_{vmtype}.tar.zst" \
           f" --tag {vmname} --tag {vmname}_{vmtype} --tag {vmtype}"


def export_lxc_vm(url: str, password: str, vmid: int, vmname: str, vmtype: str, access_key=None):
    env = {"RESTIC_PASSWORD": access_key} if access_key is not None else None
    cmd = get_env_cmd(url, password) + " && " + get_lxc_dump_cmd(vmid, vmname, vmtype)
    print(cmd)
    result = run_command(cmd, env)

    if result["code"] > 0:
        print("Error in export")
        print(result["stderr"])
        return False

    print("Export done")
    print(result["stdout"])
    return True


def export_vm(args):
    vmid = getattr(args, "vmid")
    url = getattr(args, "url")
    password = getattr(args, "password")
    access_key = getattr(args, "access_key")

    print(f"Start export VM #{vmid}")

    info = get_vm_info(vmid)

    if info is None:
        print(f"Vm with ID: {vmid} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Found {info['type']} VM id {vmid} with name {info['name']}")
    if info["type"] == "lxc":
        export_lxc_vm(url, password, vmid, info["name"], info["type"], access_key)


def import_lxc_vm(args):
    vmtype = "lxc"
    vmid = getattr(args, "vmid")
    url = getattr(args, "url")
    password = getattr(args, "password")
    access_key = getattr(args, "access_key")

    template = getattr(args, "template")
    storage = getattr(args, "storage")

    filename = f"{template}_{vmtype}.tar.zst"

    hostname = getattr(args, "hostname") or template

    size = getattr(args, "size")

    print(f"Start import {vmtype} VM #{vmid} with hostname: {hostname}) on storage: {storage} from file: {filename}")

    lxc_import_cmd = f"restic dump latest {filename}  --tag {vmtype} --tag {template}_{vmtype}" \
                     " | zstd -d -c" \
                     f" | pct restore {vmid} --hostname {hostname} --storage {storage} --rootfs {size} --unique true -"

    env = {"RESTIC_PASSWORD": access_key} if access_key is not None else None
    cmd = get_env_cmd(url, password) + " && " + lxc_import_cmd
    print(f"Command: {cmd}")
    result = run_command(cmd, env)

    if result["code"] > 0:
        print("Error in import")
        print(result["stderr"])
        return False

    print("Import done")
    print(result["stdout"])
    return True


def main():
    args = parse_args()
    if getattr(args, "ask_access_key") is True:
        access_key = getpass.getpass('Restic repository access key:')
        if access_key:
            print(f"Empty access key", file=sys.stderr)
        else:
            setattr(args, "access_key", access_key)
    try:
        result = args.func(args)
        if not result:
            print("Failed", file=sys.stderr)
            sys.exit(100)
    except Exception as e:
        print(e)


if __name__ == "__main__":
    main()
