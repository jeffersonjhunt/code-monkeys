# Playwright CLI Reference

## Test Execution

```bash
npx playwright test                    # Run all tests
npx playwright test login.spec.ts      # Run specific file
npx playwright test --grep "login"     # Filter by title
npx playwright test --project=chromium # Specific browser
npx playwright test --headed           # Show browser
npx playwright test --workers=4        # Parallel workers
npx playwright test --retries=2        # Retry failures
npx playwright test --reporter=html    # HTML report
npx playwright test --trace=on         # Collect traces
npx playwright test --debug            # Step-through debugger
npx playwright test --ui               # UI mode
```

## Code Generation

```bash
npx playwright codegen                 # Record actions
npx playwright codegen http://localhost:3000
npx playwright codegen --target=python # Generate Python
```

## Utilities

```bash
npx playwright show-report             # Open HTML report
npx playwright show-trace trace.zip    # View trace file
npx playwright install                 # Install browsers
npx playwright install chromium        # Install one browser
npx playwright screenshot <url> out.png
npx playwright pdf <url> out.pdf
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `CI` | Enables CI behaviors (forbidOnly, retries) |
| `PWDEBUG` | `1` = Playwright Inspector, `console` = debug in browser |
| `BASE_URL` | Override baseURL in config |
| `PLAYWRIGHT_BROWSERS_PATH` | Custom browser install location |

## Config Options

```typescript
defineConfig({
  testDir: './tests',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
})
```

## Common Assertions

```typescript
await expect(page).toHaveTitle(/pattern/);
await expect(page).toHaveURL('/path');
await expect(locator).toBeVisible();
await expect(locator).toHaveText('text');
await expect(locator).toHaveCount(3);
await expect(locator).toBeEnabled();
await expect(response).toBeOK();
```

## Common Actions

```typescript
await page.goto('/path');
await page.click('button');
await page.fill('input[name="email"]', 'user@test.com');
await page.selectOption('select', 'value');
await page.waitForURL('/dashboard');
await page.waitForSelector('.loaded');
await page.screenshot({ path: 'screenshot.png' });
```
