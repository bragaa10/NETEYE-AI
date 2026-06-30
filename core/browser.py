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
        if self._pw is not None:
            return
        console.print("[dim]🌐 A iniciar browser...[/dim]")
        import os
        self._pw = sync_playwright().start()
        user_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "browser_user_data")
        os.makedirs(user_data_dir, exist_ok=True)
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir,
            headless=self.headless,
            viewport={"width": 1024, "height": 600},
            locale="pt-PT",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        self._ctx.route("**/*", self._filtrar_recursos)
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        console.print("[dim green][OK] Browser pronto com contexto persistente (1024x600 otimizado).[/dim green]")

    def _filtrar_recursos(self, route, request):
        url = request.url.lower()
        # Se for YouTube ou Google, permitir recursos para evitar quebras de players de vídeo
        if "youtube.com" in url or "google.com" in url or "google" in url:
            route.continue_()
            return
        if any(b in url for b in BLOQUEAR) or request.resource_type in ("font",):
            route.abort()
        else:
            route.continue_()

    def fechar(self):
        try:
            if hasattr(self, '_page') and self._page:
                try: self._page.close()
                except Exception: pass
            if hasattr(self, '_ctx') and self._ctx:
                try: self._ctx.close()
                except Exception: pass
            if hasattr(self, '_browser') and self._browser:
                try: self._browser.close()
                except Exception: pass
            if hasattr(self, '_pw') and self._pw:
                try: self._pw.stop()
                except Exception: pass
        except Exception as e:
            console.print(f"[dim red]Erro ao fechar browser: {e}[/dim red]")
        finally:
            self._page = None
            self._ctx = None
            self._browser = None
            self._pw = None

    # ------------------------------------------------------------------
    # NAVEGAÇÃO & DETEÇÃO (Func 12)
    # ------------------------------------------------------------------

    def _obter_timeout_adaptativo(self, url: str) -> int:
        url_lower = url.lower()
        # Timeout mais longo para sites conhecidamente pesados
        if any(d in url_lower for d in ["youtube.com", "instagram.com", "facebook.com", "amazon", "linkedin.com", "twitter.com", "x.com"]):
            return 15000  # 15 segundos
        return self.timeout

    def navegar(self, url: str) -> dict:
        url = self._resolver_url(url)
        if not self._page: return {"sucesso": False, "erro": "browser não iniciado"}
        try:
            console.print(f"[dim]🌐 {url}[/dim]")
            timeout_adaptativo = self._obter_timeout_adaptativo(url)
            self._page.goto(url, timeout=timeout_adaptativo, wait_until="commit")
            try:
                if "youtube.com" in url.lower():
                    self._page.wait_for_load_state("domcontentloaded", timeout=8000)
                    try:
                        self._page.wait_for_selector("ytd-app", timeout=4000)
                    except Exception:
                        pass
                else:
                    self._page.wait_for_load_state("domcontentloaded", timeout=4000)
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
        url = f"https://www.google.com/search?q={quote_plus(consulta)}&hl=pt"
        return self.navegar(url)

    def pesquisar_youtube(self, termo: str) -> dict:
        """Pesquisa um termo no YouTube: navega para o YouTube, escreve na barra de pesquisa e submete."""
        if not self._page: return {"sucesso": False, "erro": "browser não iniciado"}
        try:
            # Se ainda não estamos no YouTube, navegar primeiro
            if "youtube.com" not in (self._page.url or "").lower():
                res = self.navegar("https://www.youtube.com")
                if not res.get("sucesso"):
                    return res

            # Seletores específicos do YouTube para a barra de pesquisa
            seletores_yt = [
                "input#search",
                "input[name='search_query']",
                "input[placeholder*='Pesquisar' i]",
                "input[placeholder*='Search' i]",
                "ytd-searchbox input",
            ]
            escrito = False
            for sel in seletores_yt:
                try:
                    el = self._page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        el.click(timeout=2000)
                        el.fill(termo)
                        escrito = True
                        break
                except Exception:
                    continue

            if not escrito:
                return {"sucesso": False, "erro": "Não consegui encontrar a barra de pesquisa do YouTube."}

            # Submeter a pesquisa
            self._page.keyboard.press("Enter")
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            self._page.wait_for_timeout(1000)
            self._auto_resolver_interrupcoes()

            return {
                "sucesso": True,
                "url": self._page.url,
                "titulo": self._obter_titulo_rapido()
            }
        except Exception as e:
            console.print(f"[red]Erro ao pesquisar YouTube: {e}[/red]")
            return {"sucesso": False, "erro": str(e)[:80]}

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
        import urllib.parse
        try:
            dominio = urllib.parse.urlparse(url).netloc
            if not dominio:
                dominio = url
        except Exception:
            dominio = url.split('/')[2] if '//' in url else url
        return f"Estás no site {dominio}, na página intitulada: {titulo}."

    def obter_estrutura_cabecalhos(self) -> dict:
        """Extrai todos os cabeçalhos (H1-H6) da página para facilitar a navegação estrutural."""
        if not self._page: return {"erro": "browser não iniciado"}
        try:
            cabecalhos = self._page.evaluate("""() => {
                const elements = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'));
                return elements.map(el => ({
                    tag: el.tagName.toLowerCase(),
                    texto: el.innerText.trim(),
                    id: el.id || ""
                })).filter(item => item.texto.length > 0);
            }""")
            return {"sucesso": True, "cabecalhos": cabecalhos}
        except Exception as e:
            return {"sucesso": False, "erro": str(e)}

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

    # Palavras/atributos que indicam que um elemento é publicidade — usados para
    # evitar clicar acidentalmente em anúncios quando o utilizador pede "o vídeo"
    # ou "o primeiro resultado" sem especificar.
    _MARCADORES_ANUNCIO = [
        "patrocinado", "sponsored", "anúncio", "anuncio", "ad ", " ad", "publicidade",
        "ad-badge", "ytd-ad-slot", "ytd-promoted", "ads-visibility",
    ]

    def _elemento_e_anuncio(self, el) -> bool:
        """Verifica heuristicamente se um elemento (ou os seus ancestrais próximos)
        parece ser um anúncio, para evitar cliques acidentais em publicidade."""
        try:
            info = el.evaluate("""(node) => {
                let cur = node;
                let texto = '';
                let classes = '';
                for (let i = 0; i < 4 && cur; i++) {
                    texto += ' ' + (cur.innerText || '').toLowerCase().slice(0, 80);
                    classes += ' ' + (cur.className || '').toString().toLowerCase();
                    classes += ' ' + (cur.tagName || '').toLowerCase();
                    cur = cur.parentElement;
                }
                return texto + ' ' + classes;
            }""")
            info_lower = (info or "").lower()
            return any(marcador in info_lower for marcador in self._MARCADORES_ANUNCIO)
        except Exception:
            return False

    def clicar_elemento(self, texto: str) -> dict:
        if not self._page: return {"sucesso": False, "erro": "browser não aberto"}
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

        texto_escaped = texto.replace("'", "\\'")
        seletores = [
            f"button:has-text('{texto_escaped}'):visible", f"a:has-text('{texto_escaped}'):visible",
            f"[aria-label*='{texto_escaped}' i]:visible", f"[role='button']:has-text('{texto_escaped}'):visible"
        ]
        for s in seletores:
            try:
                el = self._page.locator(s).first
                if el.count() > 0 and el.is_visible(timeout=500):

                    # Verificar se o elemento é provavelmente um anúncio antes de clicar.
                    # Isto evita o cenário comum de "clicaste no anúncio em vez do
                    # vídeo" quando o utilizador pede algo genérico como "o vídeo".
                    if self._elemento_e_anuncio(el):
                        console.print(f"[dim yellow]Elemento '{texto}' parece ser um anúncio — a ignorar e procurar próxima alternativa.[/dim yellow]")
                        continue

                    url_antes = self._page.url
                    dom_antes = self._page.content()
                    
                    el.click(timeout=3000)
                    
                    # Esperar estabilização do DOM ou navegação
                    try:
                        self._page.wait_for_load_state("domcontentloaded", timeout=1500)
                    except Exception:
                        pass
                    self._page.wait_for_timeout(300)
                    
                    self._auto_resolver_interrupcoes()
                    
                    url_depois = self._page.url
                    dom_depois = self._page.content()
                    
                    # Se houve alteração de URL ou mudança no conteúdo do DOM, consideramos bem-sucedido
                    if url_antes != url_depois or dom_antes != dom_depois:
                        return {"sucesso": True, "titulo_pagina": self._obter_titulo_rapido()}
                    else:
                        console.print(f"[dim yellow]Aviso: clique em {s} bem-sucedido mas sem alteração detetável no URL ou DOM.[/dim yellow]")
            except Exception as e:
                # FIX: Falhas silenciosas tornam debugging impossível em produção.
                console.print(f"[dim red]clicar_elemento falhou ({s}): {e}[/dim red]")
                continue
                
        # Tentar clique posicional
        res_pos = self._clicar_posicao(texto)
        if res_pos.get("sucesso"):
            return res_pos
            
        return {"sucesso": False, "erro": "Não foi possível clicar no elemento ou o clique não teve efeito detetável de mudança de estado na página."}

    def escrever_campo(self, label: str, texto: str) -> dict:
        seletores = []
        if label:
            label_escaped = label.replace("'", "\\'")
            seletores.extend([
                f"input[placeholder*='{label_escaped}' i]:visible", f"input[name*='{label_escaped}' i]:visible",
                f"input[aria-label*='{label_escaped}' i]:visible", f"label:has-text('{label_escaped}') + input:visible"
            ])
        # YouTube-specific search input selectors (prioritários para sites conhecidos)
        seletores.extend([
            "input#search:visible",
            "input[name='search_query']:visible",
            "ytd-searchbox input:visible",
            "input[type='search']:visible",
            "input[type='text']:visible",
            "textarea:visible",
            "input:not([type='hidden']):visible"
        ])

        for s in seletores:
            try:
                el = self._page.locator(s).first
                if el.count() > 0 and el.is_visible():
                    el.click(timeout=1500)
                    el.fill(texto)
                    self._auto_resolver_interrupcoes()
                    return {"sucesso": True}
            except Exception as e:
                # FIX: Falhas silenciosas tornam debugging impossível em produção.
                console.print(f"[dim red]escrever_campo falhou ({s}): {e}[/dim red]")
                continue
        return {"sucesso": False, "erro": "Não foi possível encontrar o campo de texto para preencher."}

    def pressionar_enter(self) -> dict:
        if not self._page: return {"sucesso": False, "erro": "browser não iniciado"}
        try:
            self._page.keyboard.press("Enter")
            try: self._page.wait_for_load_state("domcontentloaded", timeout=2000)
            except Exception: pass
            self._auto_resolver_interrupcoes()
            return {"sucesso": True}
        except Exception as e:
            console.print(f"[red]Erro ao pressionar Enter: {e}[/red]")
            return {"sucesso": False, "erro": str(e)}

    def tirar_screenshot(self) -> bytes | None:
        """
        Tira screenshot otimizado e de qualidade adequada para OCR/visão.
        Garante que a página está estável antes do screenshot.
        """
        if not self._page: return None
        try:
            # Esperar estabilização do DOM e renderização
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=2000)
                self._page.wait_for_timeout(500)
            except Exception:
                pass

            vp = self._page.viewport_size or {"width": 1024, "height": 600}
            
            # Screenshot em JPEG com qualidade 80% para garantir leitura precisa pela IA
            screenshot_bytes = self._page.screenshot(
                type="jpeg", 
                quality=80, 
                clip={
                    "x": 0, 
                    "y": 0, 
                    "width": min(vp["width"], 1024),
                    "height": min(vp["height"], 600)
                }
            )
            
            self._last_screenshot = screenshot_bytes
            return screenshot_bytes
        except Exception as e:
            console.print(f"[bold red]❌ Erro crítico ao tirar screenshot: {e}[/bold red]")
            return None

    def obter_ultima_screenshot(self) -> bytes | None:
        """Retorna a última screenshot guardada em cache (evita tirar nova)."""
        return getattr(self, '_last_screenshot', None)

    # ------------------------------------------------------------------
    # INTERNO
    # ------------------------------------------------------------------

    def _auto_resolver_interrupcoes(self):
        if not self._page: return
        # Lista alargada de botões de cookies, popups e banners comuns
        botoes = [
            # Rejeitar Cookies
            "button:has-text('Rejeitar tudo')", "a:has-text('Rejeitar tudo')",
            "button:has-text('Reject all')", "a:has-text('Reject all')",
            "button:has-text('Rejeitar')", "a:has-text('Rejeitar')",
            "button:has-text('Reject')", "a:has-text('Reject')",
            # Aceitar/Concordar Cookies
            "button:has-text('Aceitar tudo')", "a:has-text('Aceitar tudo')",
            "button:has-text('Accept all')", "a:has-text('Accept all')",
            "button:has-text('Aceitar')", "a:has-text('Aceitar')",
            "button:has-text('Accept')", "a:has-text('Accept')",
            "button:has-text('Agree')", "button:has-text('Concordo')",
            # Fechar/Cancelar/Agora não / Premium / Promos
            "button:has-text('Fechar')", "a:has-text('Fechar')",
            "button:has-text('Close')", "a:has-text('Close')",
            "button:has-text('Agora não')", "button:has-text('Not now')",
            "button:has-text('Não, obrigado')", "button:has-text('Não obrigado')",
            "button:has-text('No thanks')", "button:has-text('Skip trial')",
            "button:has-text('Ignorar')",
            # Seletores por ARIA Label
            "[aria-label*='Rejeitar tudo' i]", "[aria-label*='Reject all' i]",
            "[aria-label*='Aceitar tudo' i]", "[aria-label*='Accept all' i]",
            "[aria-label*='Fechar' i]", "[aria-label*='Close' i]",
            "[aria-label*='Não, obrigado' i]", "[aria-label*='No thanks' i]"
        ]
        seletor_combinado = ", ".join(botoes)
        try:
            el = self._page.locator(seletor_combinado).first
            # Aumentar timeout para 800ms para aguardar renderização do popup
            if el.is_visible(timeout=800):
                console.print(f"[dim yellow]Pop-up/Consentimento detetado: clicando em '{el.inner_text().strip()}'[/dim yellow]")
                el.click(timeout=1500)
                # Dar tempo para fecho do popup
                self._page.wait_for_timeout(300)
        except Exception:
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
        import urllib.parse
        return f"https://www.google.com/search?q={urllib.parse.quote_plus(alvo)}&hl=pt"

    def _clicar_posicao(self, alvo: str) -> dict:
        mapa = {"primeiro":0,"primeira":0,"segundo":1,"segunda":1,"terceiro":2}
        idx = next((i for k,i in mapa.items() if k in alvo.lower()), None)
        if idx is None: return {"sucesso": False, "erro": "Elemento posicional não mapeado."}
        try:
            els = self._page.locator("a:visible, button:visible").all()
            if len(els) > idx:
                url_antes = self._page.url
                dom_antes = self._page.content()
                
                els[idx].click(timeout=3000)
                
                try:
                    self._page.wait_for_load_state("domcontentloaded", timeout=1500)
                except Exception:
                    pass
                self._page.wait_for_timeout(300)
                self._auto_resolver_interrupcoes()
                
                url_depois = self._page.url
                dom_depois = self._page.content()
                
                if url_antes != url_depois or dom_antes != dom_depois:
                    return {"sucesso": True}
                else:
                    return {"sucesso": False, "erro": "O clique posicional não gerou alteração no estado da página."}
        except Exception as e:
            return {"sucesso": False, "erro": f"Erro no clique posicional: {e}"}
        return {"sucesso": False, "erro": "Elemento posicional correspondente não encontrado."}


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