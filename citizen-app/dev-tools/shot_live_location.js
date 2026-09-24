const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    geolocation: { latitude: 35.2280, longitude: 128.6811 },
    permissions: ["geolocation"],
  });
  const page = await context.newPage();
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));
  await page.goto("http://localhost:8000/", { waitUntil: "networkidle" });
  await page.click("#btn-allow-location");
  await page.waitForTimeout(500);
  await page.click('#age-choices .choice-card[data-value="adult"]');
  await page.waitForTimeout(200);
  await page.click('#gender-choices .choice-card[data-value="none"]');
  await page.waitForTimeout(1000);

  await page.screenshot({ path: "/tmp/shot_live_1_home_before.png" });

  // 위치를 살짝 이동 (약 150m 북쪽) -> watchPosition 콜백 발생 기대
  await context.setGeolocation({ latitude: 35.2295, longitude: 128.6811 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: "/tmp/shot_live_2_home_after_move.png" });

  // 안심경로 탭에서도 마커가 따라오는지 확인
  await page.click('.nav-item[data-tab="route"]');
  await page.waitForTimeout(400);
  await page.screenshot({ path: "/tmp/shot_live_3_route_before.png" });

  await context.setGeolocation({ latitude: 35.2310, longitude: 128.6825 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: "/tmp/shot_live_4_route_after_move.png" });

  // 위험신고 탭 위치 텍스트도 실시간 갱신되는지 확인
  await page.click('.nav-item[data-tab="report"]');
  await page.waitForTimeout(300);
  const txt1 = await page.textContent('#report-location-text');
  await context.setGeolocation({ latitude: 35.2325, longitude: 128.6840 });
  await page.waitForTimeout(800);
  const txt2 = await page.textContent('#report-location-text');
  console.log("report location before:", txt1);
  console.log("report location after :", txt2);
  await page.screenshot({ path: "/tmp/shot_live_5_report_after_move.png" });

  await browser.close();
  console.log("done");
})();
