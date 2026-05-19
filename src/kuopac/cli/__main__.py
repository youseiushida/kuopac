"""Allow ``python -m kuopac.cli`` to run the CLI through the error-trap wrapper."""
from .main import main

if __name__ == "__main__":
    main()
