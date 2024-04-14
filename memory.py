import subprocess
import os
import utils
import argparse

target_mount_point = '/mnt/tss-inter-logs'

def is_mounted(target):
    output = subprocess.run(['mount'], capture_output=True, text=True)
    
    for line in output.stdout.splitlines():
        if target in line:
            return True
    
    return False

def directory_exists(directory):
    return os.path.exists(directory)

def create_mountpoint(target_directory):
    subprocess.run(['mkdir', target_directory])

def mount_tmpfs(target_directory, size):
    size_arg = 'size='+ str(size) + 'M'
    subprocess.run(['mount', '-t', 'tmpfs', '-o', size_arg, 'tmpfs', target_directory])
    for name in utils.names:
        subprocess.run(['mkdir', os.path.join(target_directory, name)])
    subprocess.run(['chmod','-R','777', target_directory])
     
def mount(size):
    if not directory_exists(target_mount_point):
        print(f"{target_mount_point} does not exist.")
        create_mountpoint(target_directory=target_mount_point)
        print(f"{target_mount_point} hierarchy created.")
        mount_tmpfs(target_mount_point, size=size)
        print(f"{target_mount_point} has been mounted.")
    else:
        if is_mounted(target_mount_point):
            print(f"{target_mount_point} is already mounted.")
        else:
            mount_tmpfs(target_mount_point, size=size)
            print(f"{target_mount_point} has been mounted.")

def unmount():
    result = subprocess.run(['umount','-f', target_mount_point])
    subprocess.run(['rm', '-rf',  target_mount_point])
    print(f"{target_mount_point} has been successfully unmounted. folders deleted.")

parser = argparse.ArgumentParser(description='Manage tmpfs memory mounts')
parser.add_argument('--sudo', action='store_true', help='Check if the script was started with sudo')
parser.add_argument('-m', action='store_true', help='Mount tmpfs memory')
parser.add_argument('-u', action='store_true', help='Unmount tmpfs memory and delete directory')
parser.add_argument('-s', type=str, default='10', help='Size of tmpfs memory in megabytes (default: 10)')
args = parser.parse_args()

def main():
    if args.sudo or utils.is_started_with_sudo():       
        if args.m:
            try:
                int(args.s)
            except ValueError:
                print('Input correct size')
            if(int(args.s) > 5000):
                print('Memory size must be < 500M')
                return
            mount(args.s)
        elif args.u:
            unmount()
        else:
            print("No action specified. Use -m to mount or -u to unmount.")
    else:
        print("usage: sudo python memory.py <args>")


if(__name__ == '__main__'):
    main()