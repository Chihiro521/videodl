import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        from .worker import main as worker_main
        return worker_main(sys.argv[2])
    from .app import main as app_main
    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
