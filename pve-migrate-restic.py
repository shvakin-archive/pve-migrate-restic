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

    group_1 = parent_parser.add_mutually_exclusive_group(required=False)
    group_1.add_argument("-k", "--access-key", dest="access_key", type=str, help="restic access key",
                         required=False)
    group_1.add_argument("-K", "--ask-access-key", dest="ask_access_key", action='store_true',
                         help="Ask restic access key",
                         required=False)
    parent_parser.set_defaults(ask_access_key=False)

    import_export_parser = argparse.ArgumentParser(add_help=False)
    import_export_parser.add_argument("-m", "--vmid", dest="vmid", type=str, help="vmid to operation", required=True)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title="command", description="valid subcommands", help="additional help")
    subparsers.required = True

    parser_export = subparsers.add_parser("export", help="Export VM", parents=[parent_parser, import_export_parser])
    parser_export.set_defaults(func=export_vm)

    parent_parser_import = argparse.ArgumentParser(add_help=False)
    parent_parser_import.add_argument("-t", "--template", type=str, dest="template", help="template for new VM",
                                      required=True)
    parent_parser_import.add_argument("-r", "--storage", type=str, dest="storage", help="storage for new VM",
                                      required=True)
    parent_parser_import.add_argument("-f", "--force", dest="force", action='store_true',
                                      help="allow to overwrite existing VM",
                                      required=False)
    parent_parser_import.add_argument("--no-unique", dest="unique", action='store_false', default=True,
                                      help="not assign a unique random ethernet address",
                                      required=False)

    parser_import = subparsers.add_parser("import", help="Import VM")
    parser_import.set_defaults(func=import_vm)

    import_subparsers = parser_import.add_subparsers(title="vm types", description="valid import vm types",
                                                     help="additional help", dest="vmtype")
    import_subparsers.required = True

    import_lxc_parser = import_subparsers.add_parser("lxc", help="Import lxc vm",
                                                     parents=[parent_parser, import_export_parser,
                                                              parent_parser_import])

    import_lxc_parser.add_argument("-n", "--hostname", type=str, dest="hostname", help="hostname for new VM",
                                   required=False)

    import_lxc_parser.add_argument("-s", "--size", type=str, dest="size", help="root size in GB for new VM",
                                   required=True)
    import_kvm_parser = import_subparsers.add_parser("kvm", help="Import kvm VM",
                                                     parents=[parent_parser, import_export_parser,
                                                              parent_parser_import])

    parser_list = subparsers.add_parser("list", help="List Templates", parents=[parent_parser])
    parser_list.set_defaults(func=list_templates)
    parser_list.add_argument("-y", "--type", type=str, dest="vmtype", help="type vm", required=False)
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
        line = line.strip()
        if line.startswith(str(id)):
            m = re.match(r"(\d+)\s+(\w+)\s+((\w+)\s+)?([\w\-]+)", line)
            if m:
                _, status, _, lock, name = m.groups()
                info = dict(zip(("id", "status", "lock", "name", "type"), (id, status, lock, name, "lxc")))
                return info
    return None


def find_vm_kvm(id: int):
    command = "qm list"
    data = run_command(command)
    if (data["code"]) != 0:
        return None
    for line in data["stdout"].splitlines():
        line = line.strip()
        if line.startswith(str(id)):
            m = re.match(r"(\d+)\s+([\w\-]+)\s+(\w+)\s+(\d+)\s+([\d+.]+)\s+(\d+)", line)
            if m:
                _, name, status, memory, bootdisk, pid = m.groups()
                info = dict(zip(("id", "name", "status", "memory", "bootdisk", "pid", "type"),
                                (id, name, status, memory, bootdisk, pid, "kvm")))
                return info
    return None


def get_vm_info(id: int):
    return find_vm_lxc(id) or find_vm_kvm(id)


def get_env_cmd(url: str, password: str):
    return f" . env-load {url} {password}"


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

    env = {"RESTIC_PASSWORD": access_key} if access_key is not None else None

    dump_cmd = f"vzdump {vmid} --mode stop --stdout --compress zstd" \
               f" | ifne restic backup -v --stdin --stdin-filename {info['name']}_{info['type']}.tar.zst" \
               f" --tag {info['name']} --tag {info['name']}_{info['type']} --tag {info['type']}"

    full_cmd = f"{get_env_cmd(url, password)} && {dump_cmd}"
    print(full_cmd)
    result = run_command(full_cmd, env)

    print(result)

    if result["code"] > 0:
        print("Error in export")
        print(result["stderr"])
        return False

    print("Export done")
    print("MESSAGE:")
    print(result["stdout"])
    print("INFO:")
    print(result["stderr"])
    return True


def import_vm(args):
    vmtype, vmid, url, password, template, storage = (
        args.vmtype, args.vmid, args.url, args.password, args.template, args.storage)

    filename = f"{template}_{vmtype}.tar.zst"

    print(f"Try import {vmtype} VM #{vmid} on storage: {storage} from file: {filename}")

    pull_command = f"restic dump latest {filename}  --tag {vmtype} --tag {template}_{vmtype} | zstd -d -c"

    command_flags_str = f" --unique {str(args.unique).lower()} --force {str(args.force).lower()}"

    if vmtype == "lxc":
        restore_command = f"pct restore {vmid} - --hostname {args.hostname} --storage {storage} --rootfs {args.size} {command_flags_str}"
    elif vmtype == "kvm":
        restore_command = f"qmrestore - {vmid} --storage {storage} {command_flags_str}"
    else:
        raise NotImplementedError(f"Restore command for {vmtype} not implemented")

    full_command = f"{get_env_cmd(url, password)} && {pull_command} | {restore_command}"

    env = {"RESTIC_PASSWORD": args.access_key} if args.access_key is not None else None

    print(f"Command: {full_command}")

    result = run_command(full_command, env)

    if result["code"] > 0:
        print("Error in import")
        print(result["stderr"])
        return False

    print("Import done")
    print(result["stdout"])
    return True


def list_templates(args):
    url, password, vmtype = (args.url, args.password, args.vmtype)
    tag_filter = f"--tag {vmtype}" if vmtype is not None else ""
    grep = '| grep "tar.zst"'
    list_command = f"restic snapshots --last  {tag_filter}  {grep} " #--json

    full_command = f"{get_env_cmd(url, password)} && {list_command}"

    env = {"RESTIC_PASSWORD": args.access_key} if args.access_key is not None else None

    print(f"Command: {full_command}")

    result = run_command(full_command, env)

    if result["code"] > 0:
        print("Error in showing list")
        print(result["stderr"])
        return False

    info = result["stdout"]
    print("Templates:")
    for line in info.splitlines():
        _,_,_,_,_,file = line.split()
        file = file.lstrip("/")
        print(file)
    return True


def main():
    args = parse_args()
    # print(args)
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
