"""Print the FailFixer version string for use by build.bat."""
import re, pathlib

text = pathlib.Path("__init__.py").read_text()
m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
print(m.group(1) if m else "dev")
