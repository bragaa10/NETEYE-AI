"""
NetEye — core/browser.py (FUNCIONALIDADES SÉNIOR)
================================================
- Bloqueia imagens/media/analytics
- Auto-resolve cookies e popups
- [NOVO] Modo de Leitura (Extração de conteúdo principal) - Func 4
- [NOVO] Relatório "Onde estou" (Título + URL) - Func 8
- [NOVO] Deteção de Páginas de Login - Func 12
"""
import re, time
from playwright.sync_api import sync_playwright
from rich.console import Console
console = Console()

ATALHOS = {
    "google":"https://www.google.com","youtube":"https://www.youtube.com",
    "gmail":"https://mail.google.com","facebook":"https://www.facebook.com",
    "instagram":"https://www.instagram.com","wikipedia":"https://www.wikipedia.org",
    "twitter":"https://www.twitter.com","x":"https://www.x.com",
    "amazon":"https://www.amazon.es","linkedin":"https://www.linkedin.com",
}

BLOQUEAR = [
    "google-analytics","googletagmanager","doubleclick","facebook.net",
    "amazon-adsystem","googlesyndication","adservice","hotjar",
    "clarity.ms","segment.io","mixpanel","amplitude","fullstory",
]

class BrowserController:
    def __init__(self, config: dict):
        self.headless = config.get("modo_headless", False)
        self.timeout  = config.get("timeout_pagina", 8) * 1000
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    def iniciar(self):
        console.print("[dim]🌐 A iniciar browser...[/dim]")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        self._ctx = self._browser.new_context(viewport={"width": 1280, "height": 720}, locale="pt-PT")
        self._ctx.route("**/*", self._filtrar_recursos)
        self._page = self._ctx.new_page()
        console.print("[dim green]✓ Browser pronto.[/dim green]")

    def _filtrar_recursos(self, route, request):
        url = request.url.lower()
        if any(b in url for b in BLOQUEAR) or request.resource_type in ("font",):
            route.abort()
        else:
            route.continue_()

    def fechar(self):
        try:
            if self._browser: self._browser.close()
            if self._pw: self._pw.stop()
        except: pass

    # ------------------------------------------------------------------
    # NAVEGAÇÃO & DETEÇÃO (Func 12)
    # ------------------------------------------------------------------

    def navegar(self, url: str) -> dict:
        url = self._resolver_url(url)
        if not self._page: return {"sucesso": False, "erro": "browser não iniciado"}
        try:
            console.print(f"[dim]🌐 {url}[/dim]")
            self._page.goto(url, timeout=self.timeout, wait_until="commit")
            try: self._page.wait_for_load_state("domcontentloaded", timeout=4000)
            except: pass
            
            self._auto_resolver_interrupcoes()
            
            # Detetar Login (Func 12)
            tem_login = self._verificar_login()
            
            return {
                "sucesso": True, 
                "url": self._page.url, 
                "titulo": self._obter_titulo_rapido(),
                "tem_login": tem_login
            }
        except Exception as e:
            return {"sucesso": False, "url": url, "erro": str(e)[:80]}

    def _verificar_login(self) -> bool:
        """Verifica se a página atual parece ser de login."""
        try:
            # Padrão: campo password + campo texto/email + botão 'login' ou 'entrar'
            res = self._page.evaluate("""() => {
                const hasPassword = !!document.querySelector('input[type="password"]');
                const hasUser = !!document.querySelector('input[type="text"], input[type="email"]');
                const text = document.body.innerText.toLowerCase();
                const keywords = ['login', 'entrar', 'sign in', 'acceder', 'iniciar sessão'];
                const hasKeywords = keywords.some(k => text.includes(k));
                return hasPassword && hasUser && hasKeywords;
            }""")
            return bool(res)
        except: return False

    # ------------------------------------------------------------------
    # MODO LEITURA (Func 4)
    # ------------------------------------------------------------------

    def extrair_conteudo_principal(self) -> str:
        """Extrai o texto principal da página (heurística sénior)."""
        if not self._page: return ""
        try:
            # Script JS para remover ruído e extrair texto de tags semânticas
            conteudo = self._page.evaluate("""() => {
                const noise = ['nav', 'footer', 'header', 'aside', 'script', 'style', '.ads', '#ads', '.menu', '.sidebar'];
                const clone = document.body.cloneNode(true);
                noise.forEach(selector => {
                    clone.querySelectorAll(selector).forEach(el => el.remove());
                });
                
                // Priorizar tags de conteúdo
                const tags = ['article', 'main', '.content', '.post-body', '#content'];
                let root = clone;
                for (let t of tags) {
                    let el = clone.querySelector(t);
                    if (el) { root = el; break; }
                }
                
                return root.innerText.replace(/\\n{2,}/g, '\\n').trim();
            }""")
            return conteudo[:5000] # Limite para não sobrecarregar a fala
        except Exception as e:
            return f"Erro ao extrair conteúdo: {e}"

    # ------------------------------------------------------------------
    # ONDE ESTOU (Func 8)
    # ------------------------------------------------------------------

    def obter_relatorio_localizacao(self) -> str:
        """Retorna uma descrição clara da localização atual."""
        if not self._page: return "O browser não está aberto."
        titulo = self._obter_titulo_rapido() or "Sem título"
        url = self._page.url
        dominio = url.split('/')[2] if '//' in url else url
        return f"Estás no site {dominio}, na página intitulada: {titulo}."

    # ------------------------------------------------------------------
    # INTERAÇÃO MELHORADA (Bug 3)
    # ------------------------------------------------------------------

    def clicar_elemento(self, texto: str) -> dict:
        if not self._page: return {"sucesso": False}
        seletores = [
            f"text='{texto}'", f"button:has-text('{texto}')", f"a:has-text('{texto}')",
            f"[aria-label*='{texto}' i]", f"[role='button']:has-text('{texto}')"
        ]
        for s in seletores:
            try:
                el = self._page.locator(s).first
                if el.count() > 0:
                    el.click(timeout=3000)
                    self._auto_resolver_interrupcoes()
                    return {"sucesso": True}
            except: continue
        return self._clicar_posicao(texto)

    def escrever_campo(self, label: str, texto: str) -> dict:
        if not self._page: return {"sucesso": False}
        seletores = []
        if label:
            seletores.extend([
                f"input[placeholder*='{label}' i]:visible", f"input[name*='{label}' i]:visible",
                f"input[aria-label*='{label}' i]:visible", f"label:has-text('{label}') + input:visible"
            ])
        seletores.extend(["input[type='search']:visible", "input[type='text']:visible", "input:not([type='hidden']):visible"])

        for s in seletores:
            try:
                el = self._page.locator(s).first
                if el.count() > 0 and el.is_visible():
                    el.click(timeout=1500)
                    el.fill(texto)
                    return {"sucesso": True}
            except: continue
        return {"sucesso": False}

    def pressionar_enter(self) -> dict:
        try:
            self._page.keyboard.press("Enter")
            try: self._page.wait_for_load_state("domcontentloaded", timeout=2000)
            except: pass
            return {"sucesso": True}
        except: return {"sucesso": False}

    def tirar_screenshot(self) -> bytes | None:
        if not self._page: return None
        try:
            vp = self._page.viewport_size or {"width": 1280, "height": 720}
            return self._page.screenshot(type="jpeg", quality=50, 
                                        clip={"x": 0, "y": 0, "width": min(vp["width"], 800), "height": vp["height"]})
        except: return None

    # ------------------------------------------------------------------
    # INTERNO
    # ------------------------------------------------------------------

    def _auto_resolver_interrupcoes(self):
        if not self._page: return
        sequencias = ["Rejeitar tudo", "Reject all", "Fechar", "Close", "Aceitar tudo", "Accept all"]
        for label in sequencias:
            try:
                el = self._page.locator(f"button:has-text('{label}'), a:has-text('{label}')").first
                if el.is_visible(timeout=300):
                    el.click(timeout=1000)
                    time.sleep(0.3)
            except: pass

    def _obter_titulo_rapido(self) -> str:
        try: return self._page.title()
        except: return ""

    def _resolver_url(self, alvo: str) -> str:
        alvo = alvo.strip()
        if re.match(r"^https?://", alvo, re.IGNORECASE): return alvo
        for nome, url in ATALHOS.items():
            if alvo.lower() in (nome, f"o {nome}"): return url
        if "." in alvo and " " not in alvo: return f"https://{alvo}"
        return f"https://www.google.com/search?q={alvo.replace(' ','+')}&hl=pt"

    def _clicar_posicao(self, alvo: str) -> dict:
        mapa = {"primeiro":0,"primeira":0,"segundo":1,"segunda":1,"terceiro":2}
        idx = next((i for k,i in mapa.items() if k in alvo.lower()), None)
        if idx is None: return {"sucesso": False}
        try:
            els = self._page.locator("a:visible, button:visible").all()
            if len(els) > idx:
                els[idx].click(timeout=3000)
                return {"sucesso": True}
        except: pass
        return {"sucesso": False}