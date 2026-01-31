@echo off
REM Simple CLI test for keyboards expert (Windows)
REM Cost: ~$0.004

echo ==========================================
echo   Keyboards Expert CLI Test
echo ==========================================
echo.

REM Create test document
echo # Mechanical Keyboards Guide > %TEMP%\keyboard_guide.md
echo. >> %TEMP%\keyboard_guide.md
echo ## What are Mechanical Keyboards? >> %TEMP%\keyboard_guide.md
echo. >> %TEMP%\keyboard_guide.md
echo Mechanical keyboards use individual mechanical switches for each key, >> %TEMP%\keyboard_guide.md
echo providing tactile feedback and durability. >> %TEMP%\keyboard_guide.md
echo. >> %TEMP%\keyboard_guide.md
echo ## Popular Switch Types >> %TEMP%\keyboard_guide.md
echo. >> %TEMP%\keyboard_guide.md
echo 1. **Cherry MX Red** - Linear, smooth >> %TEMP%\keyboard_guide.md
echo 2. **Cherry MX Brown** - Tactile, quiet >> %TEMP%\keyboard_guide.md
echo 3. **Cherry MX Blue** - Clicky, loud >> %TEMP%\keyboard_guide.md
echo. >> %TEMP%\keyboard_guide.md
echo ## Benefits >> %TEMP%\keyboard_guide.md
echo. >> %TEMP%\keyboard_guide.md
echo - Durability (50-100 million keystrokes) >> %TEMP%\keyboard_guide.md
echo - Better typing experience >> %TEMP%\keyboard_guide.md
echo - Customizable keycaps >> %TEMP%\keyboard_guide.md

echo [OK] Created test document: %TEMP%\keyboard_guide.md
echo.

REM Create expert with learning
echo Creating expert with 1 doc + 1 quick research...
deepr expert make "Keyboards Test" --files %TEMP%\keyboard_guide.md --description "Mechanical keyboards expert" --learn --docs 1 --quick 1 --no-discovery --yes

echo.
echo [OK] Expert created
echo.

REM List experts
echo Listing experts...
deepr expert list

echo.

REM Get expert info
echo Expert details...
deepr expert info "Keyboards Test"

echo.

REM Test chat
echo Testing expert chat...
deepr chat expert "Keyboards Test" --message "What are the main types of mechanical keyboard switches?"

echo.
echo ==========================================
echo   [OK] Test Complete
echo ==========================================
echo.
echo Cleanup:
echo   deepr expert delete "Keyboards Test" --yes
echo.
echo Press any key to cleanup and exit...
pause > nul

deepr expert delete "Keyboards Test" --yes
