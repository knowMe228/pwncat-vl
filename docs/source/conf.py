# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

# -- Project information -----------------------------------------------------

project = "pwncat-vl (fork of pwncat)"
copyright = "2020, Caleb Stewart"
author = "Caleb Stewart; maintained by Chocapikk"

master_doc = "index"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "enum_tools.autoenum",
]

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_static_path = ["_static"]
