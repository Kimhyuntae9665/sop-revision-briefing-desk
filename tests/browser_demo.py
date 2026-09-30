"""Actual Chrome scenario and evidence capture for fictional P13. No model call."""
import asyncio
import json
import os
import socket
import subprocess
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PW_RUNTIME=ROOT/"artifacts"/"pw-runtime"
FFMPEG_LINK=PW_RUNTIME/"ffmpeg-1011"/"ffmpeg-linux"
FFMPEG_LINK.parent.mkdir(parents=True,exist_ok=True)
if not FFMPEG_LINK.exists(): FFMPEG_LINK.symlink_to("/usr/bin/ffmpeg")
os.environ["PLAYWRIGHT_BROWSERS_PATH"]=str(PW_RUNTIME)
from playwright.async_api import async_playwright, expect

OUT=ROOT/"artifacts"/"demo"
PORT=19114
URL=f"http://127.0.0.1:{PORT}/"


def start_server():
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1",PORT))==0:
            raise RuntimeError("port_in_use")
    proc=subprocess.Popen(["python3","-m","sop_desk.server","--port",str(PORT)],
                          cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError("server_exited:"+proc.stderr.read().decode()[:500])
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1",PORT))==0:return proc
        time.sleep(.05)
    proc.terminate()
    raise RuntimeError("server_start_timeout")


async def main():
    server=start_server()
    OUT.mkdir(parents=True,exist_ok=True)
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,executable_path="/usr/bin/google-chrome",
                                            args=["--no-sandbox"])
            context=await browser.new_context(viewport={"width":1440,"height":900},
                                              record_video_dir=str(OUT/"raw-video"),
                                              record_video_size={"width":1440,"height":900},
                                              accept_downloads=True)
            page=await context.new_page()
            await page.goto(URL,wait_until="networkidle")
            await expect(page.locator("#current-revision")).to_have_text("A")
            forged = await page.request.post(URL+"api/ack", data="{}",
                headers={"Content-Type":"application/json", "Host":"evil.example"})
            assert forged.status == 403
            await expect(page.locator("#upcoming-revision")).to_contain_text("B")
            await expect(page.locator(".diff-row")).to_have_count(5)
            assert "HAND-04" not in await page.locator("#diff-rows").inner_text()
            await expect(page.locator(".queue-card")).to_have_count(3)
            assert await page.locator(".action.primary").count()==0
            await page.screenshot(path=str(OUT/"01-a-current-b-future.png"),full_page=True)
            await asyncio.sleep(.8)
            source=page.locator(".diff-row").filter(has_text="TKT-01").locator(".source-button").last
            await source.focus()
            await page.keyboard.press("Enter")
            await expect(page.locator("#source-dialog")).to_have_attribute("open","")
            await expect(page.locator("#source-text")).to_contain_text("mes_integration")
            await page.screenshot(path=str(OUT/"02-future-source-explicit.png"),full_page=True)
            await asyncio.sleep(.8)
            await page.keyboard.press("Escape")
            await expect(page.locator("#source-dialog")).not_to_have_attribute("open","")
            assert await source.evaluate("(e)=>document.activeElement===e")
            await page.locator("#as-of").select_option("2026-10-02T00:30:00Z")
            await expect(page.locator("#current-revision")).to_have_text("B")
            await expect(page.locator(".queue-card").first).to_contain_text("배정 대기")
            assert await page.locator(".action.primary").count()==0
            await page.screenshot(path=str(OUT/"03-effective-not-assigned.png"),full_page=True)
            await asyncio.sleep(.8)
            await page.locator("#as-of").select_option("2026-10-02T02:00:00Z")
            await expect(page.locator(".queue-card").first).to_contain_text("읽음 확인 대기")
            await page.locator(".queue-card").first.locator(".action.primary").click()
            await expect(page.locator(".queue-card").first).to_contain_text("읽음 확인됨")
            await expect(page.locator("#history li")).to_have_count(3)
            await page.screenshot(path=str(OUT/"04-read-receipt-timeline.png"),full_page=True)
            await asyncio.sleep(.8)
            first=page.locator(".queue-card").first
            await first.locator("select.answer").select_option("TKT-01")
            await first.get_by_role("button",name="원문 조항 점검 기록").click()
            await expect(page.locator(".queue-card").first).to_contain_text("원문 조항 점검 기록됨")
            await expect(page.locator("#history li")).to_have_count(4)
            async with page.expect_download() as download_info:
                await page.locator(".export-button").first.click()
            download=await download_info.value
            exported=json.loads(Path(await download.path()).read_text())
            assert exported["receipt"]["revision"]=="B"
            assert exported["receipt"]["source_hash"]
            assert exported["claim_limit"].startswith("Reading")
            await page.screenshot(path=str(OUT/"05-assessment-and-export.png"),full_page=True)
            await asyncio.sleep(.8)
            # Later receipts cannot change an earlier view or satisfy its prerequisites.
            await page.locator("#as-of").select_option("2026-10-02T01:30:00Z")
            await expect(page.locator(".queue-card").first).to_contain_text("읽음 확인 대기")
            assert await page.locator("#history li").count()==2
            assert not await page.locator("#history").get_by_text("RC-",exact=False).count()
            assert await page.locator(".queue-card").first.get_by_role("button",name="원문 조항 점검 기록").count()==0
            await page.screenshot(path=str(OUT/"08-early-view-after-later-receipts.png"),full_page=True)
            await page.locator("#as-of").select_option("2026-10-02T00:30:00Z")
            await expect(page.locator(".queue-card").first).to_contain_text("배정 대기")
            assert await page.locator("#history li").count()==2
            await page.locator("#as-of").select_option("2026-10-02T02:00:00Z")
            await expect(page.locator(".queue-card").first).to_contain_text("원문 조항 점검 기록됨")
            assert await page.locator("#history li").count()==4
            older=page.locator(".diff-row").filter(has_text="TKT-01").locator(".source-button").first
            await older.click()
            await expect(page.locator("#source-meta")).to_contain_text("historical_superseded")
            await page.screenshot(path=str(OUT/"09-historical-superseded-source.png"),full_page=True)
            await page.keyboard.press("Escape")
            # A delayed prior scope response must never replace the new selection.
            async def delay_state(route):
                await asyncio.sleep(.4)
                await route.continue_()
            await page.route("**/api/state?*",delay_state)
            await page.locator("#as-of").select_option("2026-10-01T10:00:00Z")
            await page.locator("#as-of").select_option("2026-10-02T02:00:00Z")
            await expect(page.locator("#current-revision")).to_have_text("B")
            await page.wait_for_timeout(550)
            await expect(page.locator("#current-revision")).to_have_text("B")
            await page.unroute("**/api/state?*",delay_state)
            async def delay_source(route):
                await asyncio.sleep(.4)
                await route.continue_()
            await page.route("**/api/source?*",delay_source)
            await page.locator(".diff-row").filter(has_text="EVD-02").locator(".source-button").first.click()
            await expect(page.locator("#source-dialog")).to_have_attribute("open","")
            await page.locator("#role").select_option("shift_lead")
            await expect(page.locator("#current-revision")).to_have_text("B")
            await page.wait_for_timeout(500)
            assert not await page.locator("#source-dialog").evaluate("(e)=>e.open")
            await page.unroute("**/api/source?*",delay_source)
            await expect(page.locator(".queue-card")).to_have_count(3)
            assert "EVD-02" not in await page.locator("#diff-rows").inner_text()
            denied_source = await page.request.get(URL+"api/source?revision=B&clause_id=EVD-02&as_of=2026-10-02T02%3A00%3A00Z&role=shift_lead&site=DEMO-PLANT-A")
            assert denied_source.status == 403
            await page.screenshot(path=str(OUT/"06-shift-lead-briefings.png"),full_page=True)
            await asyncio.sleep(.8)
            await page.locator("#site").select_option("DEMO-PLANT-B")
            await expect(page.locator("#current-revision")).to_have_text("조회 불가")
            assert await page.locator(".diff-row").count()==0
            assert await page.locator(".queue-card").count()==0
            video=page.video
            await context.close()
            video_path=await video.path()
            out_video=OUT/"workflow.mp4"
            result=subprocess.run(["ffmpeg","-y","-loglevel","error","-i",video_path,
                                   "-c:v","libx264","-pix_fmt","yuv420p","-crf","27",
                                   "-movflags","+faststart",str(out_video)],
                                  capture_output=True,text=True)
            assert result.returncode==0,result.stderr
            mobile=await browser.new_context(viewport={"width":390,"height":844})
            phone=await mobile.new_page()
            await phone.goto(URL,wait_until="networkidle")
            await expect(phone.locator("#current-revision")).to_have_text("A")
            dims=await phone.evaluate("({scroll:document.documentElement.scrollWidth,view:innerWidth})")
            assert dims["scroll"]<=dims["view"],dims
            sizes=await phone.evaluate("""()=>({
              body:parseFloat(getComputedStyle(document.querySelector('.clause p')).fontSize),
              select:parseFloat(getComputedStyle(document.querySelector('select')).fontSize)})""")
            assert sizes["body"]>=14 and sizes["select"]>=16,sizes
            await phone.screenshot(path=str(OUT/"07-mobile-390px.png"),full_page=True)
            await mobile.close()
            await browser.close()
            print("browser: current/future, source keyboard, temporal receipt gates, superseded source, assignment gate, read, self-check, export, stale state/source, denied site, mobile PASS")
            print("mobile",dims,sizes)
            print("media",[(x.name,x.stat().st_size) for x in sorted(OUT.glob("*")) if x.is_file()])
    finally:
        server.terminate()
        try:server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill();server.wait(timeout=5)


if __name__=="__main__":
    asyncio.run(main())
