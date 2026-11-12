"""Launch existing REF Python/packages as an ordinary user, without chroot."""
import os
import sys

from proworksim.software_benchmark_ref_host_v061 import ROOT, launch_spec


def main():
    command, environment = launch_spec(sys.argv[1:])
    os.chdir(ROOT)
    os.execve(command[0], command, environment)


if __name__ == '__main__':
    main()
