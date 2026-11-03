import { existsSync } from 'node:fs'
import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: { httpCredentials: process.env.TEST_PASSWORD ? { username: process.env.TEST_USERNAME || 'admin', password: process.env.TEST_PASSWORD } : undefined, baseURL: process.env.TEST_BASE_URL || 'http://127.0.0.1:8000', headless: true,
    launchOptions: { executablePath: process.env.CHROMIUM_PATH || (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined), args: ['--no-sandbox'] } },
  reporter: 'list',
})
