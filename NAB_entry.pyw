# NAB_entry.pyw — NAB 3 entry point.
#   (default)        new web UI (nab_main)       --classic   original Tk window
#   --pdf-bot / --ocr-finder / --tool X         helper tools, each in its own process
import sys
import logging
import traceback


def _log_setup():
    try:
        import os
        d = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "NAB")
        os.makedirs(d, exist_ok=True)
        logging.basicConfig(filename=os.path.join(d, "nab.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    except Exception:
        pass


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # required for the OCR finder's process pool in a frozen EXE
    _log_setup()
    argv = sys.argv
    if "--pdf-bot" in argv:
        import nab_pdf
        nab_pdf.main()
    elif "--ocr-finder" in argv:
        import image_ocr_finder
        image_ocr_finder.main()
    elif "--tool" in argv:
        import nab_main
        nab_main.run_tool(argv[argv.index("--tool") + 1])
    elif "--classic" in argv:
        import nab_classic
        nab_classic.run()
    else:
        try:
            import nab_main
            nab_main.main()
        except SystemExit:
            raise
        except BaseException:
            logging.error("NAB web UI failed, falling back to classic:\n" + traceback.format_exc())
            import nab_classic
            nab_classic.run()
