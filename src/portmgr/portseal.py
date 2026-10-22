"""`portseal`: the sealing commands, with dckrsub chains as a fallback for the rules."""
import sys

from portmgr import sealing, secrets


def main(argv=None):
    return sealing.main(argv, resolver=secrets.dckrsub_resolver,
                        after_seal=secrets.mark_migrated_if_stack, prog="portseal")


if __name__ == "__main__":
    sys.exit(main())
