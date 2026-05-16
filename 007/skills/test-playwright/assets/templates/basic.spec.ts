import { test, expect } from '@playwright/test';

test.describe('{{NAME}}', () => {
  test('should load successfully', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/./);
  });

  test('should navigate correctly', async ({ page }) => {
    await page.goto('/');
    // Add your test steps here
    await expect(page.locator('body')).toBeVisible();
  });
});
