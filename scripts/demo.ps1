# MAWE live demo driver.
#
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
#
# Runs the demonstration one step at a time so you are never typing while
# someone watches. Before each step it prints what the step proves and the
# line to say; it then waits for Enter, so you control the pace and can stop
# anywhere to take a question.
#
#   -Short   the two steps that carry the argument on their own (~3 min)
#   -Full    adds the benchmark and the four-condition comparison (~8 min)
#
# Nothing here needs an API key or a network connection.

param(
    [switch]$Short,
    [switch]$Full
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$script:StepNumber = 0

function Write-Rule {
    Write-Host ("=" * 78) -ForegroundColor DarkCyan
}

function Show-Step {
    param(
        [string]$Title,
        [string]$Proves,
        [string]$Say,
        [string]$Command,
        [int]$Seconds
    )
    $script:StepNumber++
    Write-Host ""
    Write-Rule
    Write-Host ("  STEP {0}   {1}" -f $script:StepNumber, $Title) `
        -ForegroundColor White
    Write-Rule
    Write-Host "  Proves : $Proves" -ForegroundColor Gray
    Write-Host "  Takes  : about $Seconds seconds" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  SAY:" -ForegroundColor Yellow
    foreach ($line in $Say -split "`n") {
        Write-Host ("    " + $line.Trim()) -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "  RUN: $Command" -ForegroundColor DarkGray
    Write-Host ""
    Read-Host "  [Enter] to run, or Ctrl+C to stop here"
    Write-Host ""
    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        Write-Host ""
        Write-Host ("  NOTE: that exited with code {0}." -f $LASTEXITCODE) `
            -ForegroundColor Red
        Write-Host "  Say so plainly and move on - the report and the green" `
            -ForegroundColor Red
        Write-Host "  CI history on GitHub carry the same evidence." `
            -ForegroundColor Red
    }
    Write-Host ""
    Read-Host "  [Enter] for the next step"
}

function Invoke-TestSuite {
    # The count is read from pytest's own XML report rather than scraped
    # from the screen. pytest's "N passed" summary does not survive being
    # captured here - PowerShell drops the final chunk, so only the wall of
    # progress dots comes through - and an audience watching dots without
    # ever seeing a number is the opposite of the point of this step.
    $report = Join-Path $env:TEMP "mawe-demo-junit.xml"
    & python -m pytest -q --junit-xml="$report"
    $code = $LASTEXITCODE

    $tests = $failures = $errors = $skipped = $null
    if (Test-Path $report) {
        try {
            [xml]$parsed = Get-Content $report
            $suite = $parsed.testsuites.testsuite
            $tests = [int]$suite.tests
            $failures = [int]$suite.failures
            $errors = [int]$suite.errors
            $skipped = [int]$suite.skipped
        } catch { }
        Remove-Item $report -Force -ErrorAction SilentlyContinue
    }

    Write-Host ""
    $colour = if ($code -eq 0) { "Green" } else { "Red" }
    Write-Host ("  " + ("-" * 62)) -ForegroundColor $colour
    if ($null -ne $tests) {
        $passed = $tests - $failures - $errors - $skipped
        $headline = if ($code -eq 0) { "ALL TESTS PASSED" } else { "TESTS FAILED" }
        Write-Host ("   {0}   {1} passed, {2} failed, {3} skipped" -f `
            $headline, $passed, ($failures + $errors), $skipped) `
            -ForegroundColor $colour
        if ($skipped -gt 0) {
            Write-Host ("   Skipped tests compare our statistics against " +
                        "SciPy, which is optional.") -ForegroundColor Gray
        }
    } else {
        $headline = if ($code -eq 0) { "ALL TESTS PASSED" } else { "TESTS FAILED" }
        Write-Host ("   " + $headline) -ForegroundColor $colour
    }
    Write-Host ("  " + ("-" * 62)) -ForegroundColor $colour
    return $code
}

# --------------------------------------------------------------- preflight
Clear-Host
Write-Rule
Write-Host "  MAWE - Multi-Agent AI Workflow Engine" -ForegroundColor White
Write-Host "  Live demonstration" -ForegroundColor White
Write-Rule
Write-Host ""

$pythonOk = $null -ne (Get-Command python -ErrorAction SilentlyContinue)
if (-not $pythonOk) {
    Write-Host "  Python is not on PATH. Install it, or open the terminal" `
        -ForegroundColor Red
    Write-Host "  inside VS Code where the environment is set up." `
        -ForegroundColor Red
    exit 1
}

python -c "import mawe" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  The package is not installed in this environment." `
        -ForegroundColor Red
    Write-Host "  Run:  pip install -r requirements.txt" -ForegroundColor Red
    Write-Host "        pip install -e ." -ForegroundColor Red
    exit 1
}

Write-Host "  Python and the package are both ready." -ForegroundColor Green
Write-Host ""
Write-Host "  Before you start, say this:" -ForegroundColor Yellow
Write-Host ""
Write-Host "    'Everything is built and tested. Two of our five hypotheses" `
    -ForegroundColor Yellow
Write-Host "     are answered by measurement. The other three compare AI" `
    -ForegroundColor Yellow
Write-Host "     models against each other, and we have not run that" `
    -ForegroundColor Yellow
Write-Host "     comparison - it needs a paid API key. The machinery for it" `
    -ForegroundColor Yellow
Write-Host "     is finished.'" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Say it now, not when you are asked. A limitation you raise" `
    -ForegroundColor Gray
Write-Host "  yourself reads as rigour." -ForegroundColor Gray
Write-Host ""
Read-Host "  [Enter] to begin"

# ------------------------------------------------------------------ steps
Show-Step -Title "The test suite" `
    -Proves "the whole project works, on three Python versions in CI" `
    -Seconds 60 `
    -Say @"
This is the entire project under test. No API key, no network, nothing
costs anything. The same suite runs on Python 3.11, 3.12 and 3.13 on
GitHub's servers every time we push.
"@ `
    -Command "Invoke-TestSuite"

Show-Step -Title "Watch the three agents work" `
    -Proves "the pipeline does what the poster says it does" `
    -Seconds 20 `
    -Say @"
The Product Manager writes a specification with runnable checks. The
Developer implements it. The Reviewer actually runs the code in a sandbox
and compares the real output to the spec - it does not read the code and
give an opinion. Watch the first review reject it for a specific reason,
and the second attempt fix that exact thing.
"@ `
    -Command "python -m mawe.cli `"Build a terminal snake game`" --verbose"

if ($Short) {
    Write-Host ""
    Write-Rule
    Write-Host "  That is the short demo. A and B carry the argument." `
        -ForegroundColor White
    Write-Host "  Run with -Full for the benchmark and the comparison." `
        -ForegroundColor Gray
    Write-Rule
    exit 0
}

Show-Step -Title "The loop always terminates" `
    -Proves "the computer-science contribution, measured not argued" `
    -Seconds 5 `
    -Say @"
Two agents disagreeing is an infinite loop, and a loop that does not stop
burns the whole API budget overnight. We push a hundred thousand randomised
adversarial review sequences through the routing policy. None fail to
terminate, none exceed their iteration cap.
"@ `
    -Command "python scripts/week6_loop_stress.py"

Show-Step -Title "How this is tested with no API key" `
    -Proves "the mock is a design decision, not a shortcut" `
    -Seconds 20 `
    -Say @"
If you are wondering how a project that has never called a language model
can claim to be tested - testing the machinery around a model and testing
the quality of a model are two different jobs. This shows the difference
rather than arguing it.
"@ `
    -Command "python scripts/how_we_test.py"

if (-not $Full) {
    Write-Host ""
    Write-Rule
    Write-Host "  Core demo finished. Run with -Full for the benchmark" `
        -ForegroundColor White
    Write-Host "  validation and the four-condition comparison." `
        -ForegroundColor Gray
    Write-Rule
    exit 0
}

Show-Step -Title "The benchmark is a valid instrument" `
    -Proves "we measured our measuring tool instead of trusting it" `
    -Seconds 120 `
    -Say @"
Twenty tasks with hidden tests the agents never see, so the score does not
depend on our own reviewing model - a run our Reviewer approved can still
score zero. And we test the benchmark itself: every task is solvable, no
task can be passed by a program that does nothing, and when we inject
deliberate bugs into the reference solutions the hidden tests catch most
of them.
"@ `
    -Command "python scripts/week9_bench_check.py --quick"

Show-Step -Title "The four-condition comparison" `
    -Proves "the experiment pipeline detects a difference it was built to detect" `
    -Seconds 90 `
    -Say @"
Four conditions: a single model, a single model that revises its own code,
our engine, and our engine with memory compression switched off. Say this
out loud - these numbers come from a fixture with known answers, not a real
model. It shows the experiment works. It says nothing about any model's
ability, and the script prints that warning itself.
"@ `
    -Command "python scripts/week11_experiment.py --tasks fizzbuzz palindrome json-query"

Write-Host ""
Write-Rule
Write-Host "  Demo finished." -ForegroundColor White
Write-Rule
Write-Host ""
Write-Host "  If he asks what is left:" -ForegroundColor Yellow
Write-Host ""
Write-Host "    'One sweep against a real model - 240 runs, about an hour of" `
    -ForegroundColor Yellow
Write-Host "     compute. The benchmark, the baselines and the statistics are" `
    -ForegroundColor Yellow
Write-Host "     all finished and validated. What is missing is the key, not" `
    -ForegroundColor Yellow
Write-Host "     the code.'" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Hand over: docs\reports\FINAL-REPORT.pdf" -ForegroundColor Gray
Write-Host "             docs\poster\MAWE-URC-Poster-with-results.pdf" `
    -ForegroundColor Gray
Write-Host "             the GitHub link" -ForegroundColor Gray
Write-Host ""
