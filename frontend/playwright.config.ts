import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  outputDir: '../.local/playwright',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:18082/ai-learn/', viewport: { width: 390, height: 844 }, trace: 'retain-on-failure' },
})
