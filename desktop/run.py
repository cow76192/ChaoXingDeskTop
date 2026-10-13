import sys

if __name__ == "__main__":
    if "--worker" in sys.argv:
        from chaoxing_desktop.worker import main
        raise SystemExit(main())
    from chaoxing_desktop.gui import main
    raise SystemExit(main())
