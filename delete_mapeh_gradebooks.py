"""Legacy cleanup entry point; preview only, never delete school records."""

if __name__ == "__main__":
    from backend.tools.preview_mapeh_cleanup import main
    raise SystemExit(main(subsubjects=True))
