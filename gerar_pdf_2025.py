"""Gera PDF do relatório 2025 com todas as páginas."""
import os, datetime
from playwright.sync_api import sync_playwright

HTML = "/Users/lucasbarros/rotina-nfp/relatorio_atual.html"
PDF  = "/Users/lucasbarros/rotina-nfp/01.2025-12.2025_Estudo NFP - AFESU.pdf"

CSS = """
    html, body { overflow: visible !important; height: auto !important; }
    #slider { display: block !important; overflow: visible !important; width: auto !important; height: auto !important; }
    .slide { width: 100% !important; height: auto !important; min-height: 100vh !important; overflow: visible !important; page-break-after: always !important; break-after: page !important; }
    #nav { display: none !important; }
"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.goto(f"file://{HTML}")
    page.wait_for_timeout(3000)
    page.add_style_tag(content=CSS)
    page.wait_for_timeout(500)
    page.pdf(path=PDF, landscape=True, format="A4", print_background=True)
    browser.close()

tamanho = os.path.getsize(PDF)
print(f"PDF gerado: {PDF}")
print(f"Tamanho: {tamanho:,} bytes")
print(f"Modificado: {datetime.datetime.fromtimestamp(os.path.getmtime(PDF))}")
