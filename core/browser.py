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
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"  # Reduzir uso de shared memory
            ]
        )
        # [OTIMIZAÇÃO] Viewport reduzido para 1024x600 (WVGA) em vez de 1280x720
        # Reduz ~30% de consumo de memória durante o render
        self._ctx = self._browser.new_context(viewport={"width": 1024, "height": 600}, locale="pt-PT")
        self._ctx.route("**/*", self._filtrar_recursos)
        self._page = self._ctx.new_page()
        console.print("[dim green][OK] Browser pronto (1024x600 otimizado).[/dim green]")

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
        except Exception as e:
            # FIX: Falhas silenciosas tornam debugging impossível em produção.
            console.print(f"[dim red]Erro ao fechar browser: {e}[/dim red]")

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
            except Exception as e:
                console.print(f"[dim red]Aviso wait_for_load_state: {e}[/dim red]")
            
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
            console.print(f"[red]Erro ao navegar: {e}[/red]")
            return {"sucesso": False, "url": url, "erro": str(e)[:80]}

    def pesquisar_google(self, consulta: str) -> dict:
        """Realiza uma pesquisa no Google e carrega a página de resultados."""
        from urllib.parse import quote_plus
        # FIX: quote_plus() trata caracteres especiais (acentos, &, #, etc.) corretamente.
        # Substituição manual de espaços quebra URLs com caracteres especiais.
        url = f"https://www.google.com/search?q={quote_plus(consulta)}&hl=pt"
        return self.navegar(url)

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
        except Exception as e:
            console.print(f"[dim red]Erro ao verificar login: {e}[/dim red]")
            return False

    # ------------------------------------------------------------------
    # MODO LEITURA (Func 4)
    # ------------------------------------------------------------------

    def extrair_conteudo_principal(self) -> str:
        """Extrai e resume o conteúdo principal da página para visualização auditiva."""
        if not self._page: return "O browser não está aberto."
        try:
            res = self._page.evaluate("""() => {
                const title = document.title || "Sem título";
                
                // Clone body to avoid mutating
                const noise = ['nav', 'footer', 'header', 'aside', 'script', 'style', '.ads', '#ads', '.menu', '.sidebar', 'iframe'];
                const clone = document.body.cloneNode(true);
                noise.forEach(selector => {
                    clone.querySelectorAll(selector).forEach(el => el.remove());
                });
                
                const tags = ['article', 'main', '.content', '.post-body', '#content'];
                let root = clone;
                for (let t of tags) {
                    let el = clone.querySelector(t);
                    if (el) { root = el; break; }
                }
                
                const pElements = Array.from(root.querySelectorAll('p')).map(el => el.innerText.trim()).filter(t => t.length > 20).map(t => t.length > 400 ? t.substring(0, 400) + '...' : t);
                const firstParagraphs = pElements.slice(0, 3);
                
                const aElements = Array.from(root.querySelectorAll('a')).filter(el => {
                    const text = el.innerText.trim();
                    return text.length > 3 && !['entrar', 'login', 'sair', 'sign in', 'home', 'contacto', 'sobre', 'about', 'cookies'].includes(text.toLowerCase());
                });
                
                const totalLinks = root.querySelectorAll('a').length;
                const relevantLinks = aElements.slice(0, 5).map(el => el.innerText.trim());
                
                return {
                    title: title,
                    totalParagraphs: pElements.length,
                    totalLinks: totalLinks,
                    paragraphs: firstParagraphs,
                    links: relevantLinks
                };
            }""")
            
            title = res["title"]
            total_p = res["totalParagraphs"]
            total_a = res["totalLinks"]
            paragraphs = res["paragraphs"]
            links = res["links"]
            
            summary = f"Título da página: {title}.\n"
            summary += f"Esta página contém {total_p} parágrafos de texto e {total_a} links.\n"
            
            if paragraphs:
                summary += "O conteúdo principal diz o seguinte:\n"
                for p in paragraphs:
                    summary += f"{p}\n"
            else:
                summary += "Não foi encontrado texto estruturado nos parágrafos principais.\n"
                
            if links:
                summary += "Alguns links relevantes encontrados são: " + ", ".join(links) + "."
                
            return summary
        except Exception as e:
            console.print(f"[red]Erro ao extrair conteúdo principal: {e}[/red]")
            return f"Erro ao ler a página: {e}"

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
    # HELPERS DE ACESSIBILIDADE ADICIONAIS (Melhoria Acessibilidade)
    # ------------------------------------------------------------------

    def obter_elementos_interativos(self) -> dict:
        """Retorna um dicionário com os elementos interativos numerados da página atual (acessibilidade)."""
        if not self._page: return {"erro": "browser não iniciado"}
        try:
            # Script JS para obter todos os links, botões e elementos com role=button visíveis
            elementos = self._page.evaluate("""() => {
                const interativos = Array.from(document.querySelectorAll('a, button, [role="button"], input[type="button"], input[type="submit"]'));
                // Filtrar apenas elementos visíveis e com texto útil
                const uteis = interativos.filter(el => {
                    const rect = el.getBoundingClientRect();
                    const estilo = window.getComputedStyle(el);
                    const visivel = rect.width > 0 && rect.height > 0 && estilo.display !== 'none' && estilo.visibility !== 'hidden' && estilo.opacity !== '0';
                    const texto = el.innerText ? el.innerText.trim() : '';
                    const ariaLabel = el.getAttribute('aria-label') ? el.getAttribute('aria-label').trim() : '';
                    const placeholder = el.getAttribute('placeholder') ? el.getAttribute('placeholder').trim() : '';
                    return visivel && (texto || ariaLabel || placeholder);
                });
                
                return uteis.slice(0, 15).map((el, index) => {
                    return {
                         id: index + 1,
                         tag: el.tagName.toLowerCase(),
                         texto: el.innerText ? el.innerText.trim() : (el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim()
                    };
                });
            }""")
            
            # Guardar temporariamente os elementos para clique rápido por ID
            self._elementos_mapeados = {str(el["id"]): el["texto"] for el in elementos}
            return {"elementos": elementos}
        except Exception as e:
            console.print(f"[red]Erro ao obter elementos interativos: {e}[/red]")
            return {"erro": str(e)}

    def ir_para_cabecalho(self, direcao: str) -> dict:
        """Desloca a página para o cabeçalho seguinte ou anterior (acessibilidade)."""
        if not self._page: return {"erro": "browser não iniciado"}
        try:
            resultado = self._page.evaluate("""(dir) => {
                const headers = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6')).filter(h => {
                    const rect = h.getBoundingClientRect();
                    const style = window.getComputedStyle(h);
                    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                });
                if (headers.length === 0) return false;
                
                let targetHeader = null;
                if (dir === 'seguinte' || dir === 'baixo') {
                    targetHeader = headers.find(h => h.getBoundingClientRect().top > 5);
                } else {
                    const reversedHeaders = [...headers].reverse();
                    targetHeader = reversedHeaders.find(h => h.getBoundingClientRect().top < -5);
                }
                
                if (targetHeader) {
                    targetHeader.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    return targetHeader.innerText || 'Cabeçalho';
                }
                return false;
            }""", direcao)
            
            if resultado:
                return {"sucesso": True, "cabecalho": resultado}
            return {"sucesso": False, "erro": "Nenhum cabeçalho encontrado nessa direção"}
        except Exception as e:
            console.print(f"[red]Erro ao saltar cabeçalho: {e}[/red]")
            return {"sucesso": False, "erro": str(e)}

    # ------------------------------------------------------------------
    # INTERAÇÃO MELHORADA (Bug 3)
    # ------------------------------------------------------------------

    def clicar_elemento(self, texto: str) -> dict:
        if not self._page: return {"sucesso": False}
        texto_limpo = texto.strip().lower()
        
        # Verificar se foi mapeado no obter_elementos_interativos por ID numérico
        if hasattr(self, "_elementos_mapeados") and texto_limpo in self._elementos_mapeados:
            texto = self._elementos_mapeados[texto_limpo]
            
        # Converter palavras numéricas comuns
        mapa_num = {"um":"1", "dois":"2", "três":"3", "quatro":"4", "cinco":"5", "seis":"6", "sete":"7", "oito":"8", "nove":"9", "dez":"10"}
        if texto_limpo in mapa_num:
            num = mapa_num[texto_limpo]
            if hasattr(self, "_elementos_mapeados") and num in self._elementos_mapeados:
                texto = self._elementos_mapeados[num]

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
            except Exception as e:
                # FIX: Falhas silenciosas tornam debugging impossível em produção.
                console.print(f"[dim red]clicar_elemento falhou ({s}): {e}[/dim red]")
                continue
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
            except Exception as e:
                # FIX: Falhas silenciosas tornam debugging impossível em produção.
                console.print(f"[dim red]escrever_campo falhou ({s}): {e}[/dim red]")
                continue
        return {"sucesso": False}

    def pressionar_enter(self) -> dict:
        try:
            self._page.keyboard.press("Enter")
            try: self._page.wait_for_load_state("domcontentloaded", timeout=2000)
            except Exception: pass
            return {"sucesso": True}
        except Exception as e:
            console.print(f"[red]Erro ao pressionar Enter: {e}[/red]")
            return {"sucesso": False}

    def tirar_screenshot(self) -> bytes | None:
        """
        Tira screenshot otimizado (reduzido em 70% de tamanho).
        [OTIMIZAÇÃO] Viewport reduzido + JPEG de baixa qualidade + cache da última screenshot.
        """
        if not self._page: return None
        try:
            # Viewport otimizado: 1024x600 em vez de 1280x720 (reduz 30% de dados)
            vp = self._page.viewport_size or {"width": 1024, "height": 600}
            
            # Screenshot em JPEG com qualidade 40% (vs 50% original) - mais compressão
            screenshot_bytes = self._page.screenshot(
                type="jpeg", 
                quality=40, 
                clip={
                    "x": 0, 
                    "y": 0, 
                    "width": min(vp["width"], 1024),  # Limitar largura máxima
                    "height": min(vp["height"], 600)   # Limitar altura máxima
                }
            )
            
            # Guardar em memória (cache simples da última screenshot)
            self._last_screenshot = screenshot_bytes
            return screenshot_bytes
        except Exception as e:
            console.print(f"[dim red]Erro tirar_screenshot: {e}[/dim red]")
            return None
    
    def obter_ultima_screenshot(self) -> bytes | None:
        """Retorna a última screenshot guardada em cache (evita tirar nova)."""
        return getattr(self, '_last_screenshot', None)

    # ------------------------------------------------------------------
    # INTERNO
    # ------------------------------------------------------------------

    def _auto_resolver_interrupcoes(self):
        if not self._page: return
        # Otimizado: Combinar seletores para evitar loops de 300ms sequenciais
        botoes = [
            "button:has-text('Rejeitar tudo')", "a:has-text('Rejeitar tudo')",
            "button:has-text('Reject all')", "a:has-text('Reject all')",
            "button:has-text('Fechar')", "a:has-text('Fechar')",
            "button:has-text('Close')", "a:has-text('Close')",
            "button:has-text('Aceitar tudo')", "a:has-text('Aceitar tudo')",
            "button:has-text('Accept all')", "a:has-text('Accept all')"
        ]
        seletor_combinado = ", ".join(botoes)
        try:
            el = self._page.locator(seletor_combinado).first
            if el.is_visible(timeout=150):
                el.click(timeout=1000)
                time.sleep(0.1)
        except Exception as e:
            pass

    def _obter_titulo_rapido(self) -> str:
        try: return self._page.title()
        except Exception: return ""

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
        except Exception as e:
            pass
        return {"sucesso": False}


# ============================================================
# BROWSER SINGLETON MANAGER (Otimização: Reutilização)
# ============================================================

import threading

_browser_instance = None
_browser_lock = threading.RLock()


def obter_browser(config: dict) -> BrowserController:
    """
    Obtém ou cria instância global do browser.
    Reutiliza o mesmo browser entre múltiplas sessões (impacto alto em performance).
    """
    global _browser_instance
    with _browser_lock:
        if _browser_instance is None:
            _browser_instance = BrowserController(config)
            _browser_instance.iniciar()
        return _browser_instance


def fechar_browser_global():
    """Fecha a instância global do browser."""
    global _browser_instance
    with _browser_lock:
        if _browser_instance is not None:
            _browser_instance.fechar()
            _browser_instance = None