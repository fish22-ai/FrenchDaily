import py_compile, sys
files = [
    'core/__init__.py', 'core/models.py', 'core/streak.py',
    'core/dict_lookup.py', 'core/tts.py', 'core/llm.py',
    'core/html.py', 'fetchers/__init__.py', 'scripts/build.py',
]
ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print('  OK  ' + f)
    except py_compile.PyCompileError as e:
        print('  FAIL ' + f + ': ' + str(e))
        ok = False
print('\nAll OK' if ok else '\nERRORS')
sys.exit(0 if ok else 1)
