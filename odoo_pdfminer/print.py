from pdfminer.high_level import extract_text
import sys
print(extract_text(sys.argv[1]))