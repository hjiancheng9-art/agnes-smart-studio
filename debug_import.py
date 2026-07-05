import sys, traceback
sys.path.insert(0, r'C:\Users\huangjiancheng\agnes-smart-studio')
try:
    from core.observability import Tracer
except:
    with open('output/import_error.txt', 'w') as f:
        traceback.print_exc(file=f)
print("Error written to output/import_error.txt")
