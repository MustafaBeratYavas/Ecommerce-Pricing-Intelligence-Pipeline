"""Repository filesystem anchors shared across runtime layers.

This module centralizes path discovery so services can resolve configuration,
database, log, and report locations without depending on the caller's working
directory.
"""

import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
