const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    geolocation: { latitude: 35.2280, longitude: 128.6811 },
    permissions: ["geolocation"],
  });
  const page = await context.newPage();
  page.on("console", (msg) => console.log("[console]", msg.type(), msg.text()));
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));
  await page.goto("http://localhost:8000/", { waitUntil: "networkidle" });

  // 1. onboarding - location step
  await page.screenshot({ path: "/tmp/shot_1_onboarding_location.png" });

  await page.click("#btn-allow-location");
  await page.waitForTimeout(600);
  await page.screenshot({ path: "/tmp/shot_2_onboarding_age.png" });

  await page.click('#age-choices .choice-card[data-value="child"]');
  await page.waitForTimeout(300);
  await page.screenshot({ path: "/tmp/shot_3_onboarding_gender.png" });

  await page.click('#gender-choices .choice-card[data-value="female"]');
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "/tmp/shot_4_home.png" });

  await page.click('.nav-item[data-tab="route"]');
  await page.waitForTimeout(500);
  await page.screenshot({ path: "/tmp/shot_5_route.png" });

  await page.fill("#route-end", "상남도서관");
  await page.waitForTimeout(200);
  await page.screenshot({ path: "/tmp/shot_5b_route_suggestions.png" });
  await page.click("#route-end-suggestions li");
  await page.waitForTimeout(150);
  await page.click("#btn-find-route");
  await page.waitForTimeout(400);
  await page.screenshot({ path: "/tmp/shot_5c_route_loading.png" });
  await page.waitForSelector("#route-options:not([hidden])", { timeout: 8000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: "/tmp/shot_6_route_options.png" });

  // 균형 옵션으로 전환해서 하이라이트가 바뀌는지 확인
  await page.click('.route-option[data-type="balanced"]');
  await page.waitForTimeout(300);
  await page.screenshot({ path: "/tmp/shot_6b_route_balanced.png" });

  await page.click('.nav-item[data-tab="report"]');
  await page.waitForTimeout(300);
  await page.screenshot({ path: "/tmp/shot_7_report.png" });

  await page.selectOption("#report-type", "dark_alley");
  await page.fill("#report-desc", "가로등이 꺼져 있어서 밤에 너무 어두워요.");
  await page.waitForTimeout(200);
  await page.screenshot({ path: "/tmp/shot_8_report_filled.png" });

  await page.click('.nav-item[data-tab="save"]');
  await page.waitForTimeout(200);
  await page.screenshot({ path: "/tmp/shot_9_save.png" });

  await browser.close();
  console.log("done");
})();
