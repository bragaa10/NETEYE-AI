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

# Domínios que servem CONTEÚDO essencial (vídeo, imagens de player, fontes da própria
# plataforma) e que NUNCA devem ser bloqueados, mesmo que não sejam "youtube.com"/"google.com"
# literalmente. Sem isto, o stream de vídeo do YouTube (servido por googlevideo.com) cai
# no filtro genérico de baixo e pode ser atrasado, prejudicando diretamente a experiência
# auditiva de quem depende do áudio a tocar sem demoras.
PERMITIR_SEMPRE = [
    "youtube.com", "ytimg.com", "googlevideo.com", "ggpht.com",
    "google.com", "gstatic.com", "googleapis.com", "googleusercontent.com",
]

BLOQUEAR = [
    "google-analytics", "googletagmanager", "doubleclick", "facebook.net",
    "amazon-adsystem", "googlesyndication", "adservice", "hotjar",
    "clarity.ms", "segment.io", "mixpanel", "amplitude", "fullstory",
    "scorecardresearch", "quantserve", "criteo", "taboola", "outbrain",
    "adnxs", "pubmatic", "rubiconproject", "casalemedia",
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
        import platform
        self._pw = sync_playwright().start()
        user_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "browser_user_data")
        os.makedirs(user_data_dir, exist_ok=True)

        # --no-sandbox e --disable-dev-shm-usage existem para mitigar limitações de
        # containers/Linux. Em Windows não trazem benefício e podem, em alguns casos,
        # desativar otimizações do Chromium — por isso só se aplicam fora do Windows.
        args = ["--disable-blink-features=AutomationControlled"]
        if platform.system() != "Windows":
            args.extend(["--no-sandbox", "--disable-dev-shm-usage"])

        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir,
            headless=self.headless,
            viewport={"width": 1024, "height": 600},
            locale="pt-PT",
            args=args
        )
        self._ctx.route("**/*", self._filtrar_recursos)
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        console.print("[dim green][OK] Browser pronto com contexto persistente (1024x600 otimizado).[/dim green]")

    def _filtrar_recursos(self, route, request):
        url = request.url.lower()
        # Domínios essenciais da própria plataforma (incl. CDN de vídeo do YouTube) —
        # nunca bloquear, para não atrasar/quebrar o carregamento de vídeo.
        if any(d in url for d in PERMITIR_SEMPRE):
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
        url_resolvido = self._resolver_url(url)
        if url_resolvido is None:
            # O alvo pedido não fazia sentido como URL nem como termo de pesquisa
            # (ex: a IA tentou navegar para "about:blank" por falta da ferramenta
            # certa). Recusar explicitamente em vez de pesquisar algo sem sentido
            # no Google — isso confundiria um utilizador que só ouve a resposta.
            console.print(f"[yellow]⚠️ navegar() recusou alvo sem sentido: '{url}'[/yellow]")
            return {
                "sucesso": False,
                "erro": "alvo_invalido",
                "mensagem": "Esse pedido não corresponde a um site válido. Diz-me o nome do site ou o que queres pesquisar."
            }
        url = url_resolvido
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
            
            titulo = self._obter_titulo_rapido()
            self._registar_memoria("pagina", titulo or self._page.url, {"acao": "navegar"})
            return {
                "sucesso": True, 
                "url": self._page.url, 
                "titulo": titulo,
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

    # ------------------------------------------------------------------
    # ESTADO, MEMÓRIA E VERIFICAÇÃO PÓS-AÇÃO
    # ------------------------------------------------------------------

    def _estado_pagina(self) -> dict:
        if not self._page:
            return {"url": "", "titulo": "", "assinatura": "", "scroll_y": 0}
        try:
            return self._page.evaluate("""() => {
                const texto = (document.body && document.body.innerText || '').replace(/\s+/g, ' ').trim();
                const focado = document.activeElement ? [
                    document.activeElement.tagName,
                    document.activeElement.getAttribute('type') || '',
                    document.activeElement.getAttribute('name') || '',
                    document.activeElement.getAttribute('aria-label') || '',
                    document.activeElement.value || ''
                ].join('|') : '';
                return {
                    url: location.href,
                    titulo: document.title || '',
                    assinatura: texto.slice(0, 4000) + '|' + document.body.childElementCount + '|' + focado,
                    scroll_y: Math.round(window.scrollY || 0)
                };
            }""")
        except Exception:
            return {"url": getattr(self._page, "url", ""), "titulo": self._obter_titulo_rapido(), "assinatura": "", "scroll_y": 0}

    def _estado_mudou(self, antes: dict, depois: dict, aceitar_mesma_pagina: bool = True) -> bool:
        if not antes or not depois:
            return False
        if antes.get("url") != depois.get("url") or antes.get("titulo") != depois.get("titulo"):
            return True
        if aceitar_mesma_pagina and antes.get("assinatura") != depois.get("assinatura"):
            return True
        if aceitar_mesma_pagina and antes.get("scroll_y") != depois.get("scroll_y"):
            return True
        return False

    def _aguardar_pos_acao(self):
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=2000)
        except Exception:
            pass
        try:
            self._page.wait_for_timeout(350)
        except Exception:
            pass
        self._auto_resolver_interrupcoes()

    def _registar_memoria(self, tipo: str, texto: str, metadata: dict | None = None):
        texto = (texto or "").strip()
        if not texto:
            return
        item = {
            "tipo": tipo,
            "texto": texto[:220],
            "url": self._page.url if self._page else "",
            "titulo": self._obter_titulo_rapido() if self._page else "",
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        self._memoria_navegacao.append(item)
        self._memoria_navegacao = self._memoria_navegacao[-self._limite_memoria:]

    def obter_memoria_navegacao(self) -> dict:
        memoria = []
        agora = time.time()
        for item in reversed(self._memoria_navegacao[-self._limite_memoria:]):
            copia = item.copy()
            copia["ha_segundos"] = int(agora - item.get("timestamp", agora))
            memoria.append(copia)
        return {"sucesso": True, "memoria": memoria}

    def _normalizar_id_numerico(self, valor: str) -> str | None:
        texto = (valor or "").strip().lower()
        mapa_num = {
            "um": "1", "uma": "1", "primeiro": "1", "primeira": "1",
            "dois": "2", "duas": "2", "segundo": "2", "segunda": "2",
            "três": "3", "tres": "3", "terceiro": "3", "terceira": "3",
            "quatro": "4", "cinco": "5", "seis": "6", "sete": "7", "oito": "8", "nove": "9", "dez": "10"
        }
        if texto.isdigit():
            return texto
        return mapa_num.get(texto)

    # ------------------------------------------------------------------
    # NAVEGAÇÃO HISTÓRICA (voltar / avançar / recarregar)
    # ------------------------------------------------------------------
    # Estas ferramentas existem para que pedidos como "volta atrás", "avança",
    # ou "recarrega a página" tenham uma ação real e determinística — sem elas,
    # a IA era forçada a inventar valores sem sentido (ex: navegar para
    # "about:blank") quando não tinha forma de cumprir o pedido, o que para um
    # utilizador que não vê o ecrã resultava em navegação destrutiva e
    # silenciosa para uma página completamente diferente da esperada.

    def voltar_pagina(self) -> dict:
        """Volta para a página anterior no histórico de navegação do browser."""
        if not self._page: return {"sucesso": False, "erro": "browser não iniciado"}
        try:
            antes = self._estado_pagina()
            resp = self._page.go_back(timeout=self.timeout, wait_until="commit")
            if resp is None:
                return {"sucesso": False, "erro": "Não há nenhuma página anterior no histórico."}
            self._aguardar_pos_acao()
            depois = self._estado_pagina()
            if not self._estado_mudou(antes, depois, aceitar_mesma_pagina=False):
                return {"sucesso": False, "erro": "O comando voltar não alterou a página; pode não haver histórico anterior."}
            self._registar_memoria("pagina", depois.get("titulo") or depois.get("url"), {"acao": "voltar"})
            return {"sucesso": True, "url": depois.get("url"), "titulo": depois.get("titulo")}
        except Exception as e:
            console.print(f"[red]Erro ao voltar página: {e}[/red]")
            return {"sucesso": False, "erro": "Não foi possível voltar à página anterior."}

    def avancar_pagina(self) -> dict:
        """Avança para a próxima página no histórico de navegação do browser (oposto de voltar)."""
        if not self._page: return {"sucesso": False, "erro": "browser não iniciado"}
        try:
            antes = self._estado_pagina()
            resp = self._page.go_forward(timeout=self.timeout, wait_until="commit")
            if resp is None:
                return {"sucesso": False, "erro": "Não há nenhuma página seguinte no histórico."}
            self._aguardar_pos_acao()
            depois = self._estado_pagina()
            if not self._estado_mudou(antes, depois, aceitar_mesma_pagina=False):
                return {"sucesso": False, "erro": "O comando avançar não alterou a página; pode não haver histórico seguinte."}
            self._registar_memoria("pagina", depois.get("titulo") or depois.get("url"), {"acao": "avancar"})
            return {"sucesso": True, "url": depois.get("url"), "titulo": depois.get("titulo")}
        except Exception as e:
            console.print(f"[red]Erro ao avançar página: {e}[/red]")
            return {"sucesso": False, "erro": "Não foi possível avançar para a página seguinte."}

    def recarregar_pagina(self) -> dict:
        """Recarrega a página atual (equivalente a F5 / botão atualizar)."""
        if not self._page: return {"sucesso": False, "erro": "browser não iniciado"}
        try:
            antes = self._estado_pagina()
            self._page.reload(timeout=self.timeout, wait_until="commit")
            self._aguardar_pos_acao()
            depois = self._estado_pagina()
            if not depois.get("url"):
                return {"sucesso": False, "erro": "Não consegui confirmar o estado da página depois de recarregar."}
            mudou = self._estado_mudou(antes, depois, aceitar_mesma_pagina=True)
            self._registar_memoria("pagina", depois.get("titulo") or depois.get("url"), {"acao": "recarregar", "mudanca_detectada": mudou})
            return {"sucesso": True, "url": depois.get("url"), "titulo": depois.get("titulo"), "mudanca_detectada": mudou}
        except Exception as e:
            console.print(f"[red]Erro ao recarregar página: {e}[/red]")
            return {"sucesso": False, "erro": "Não foi possível recarregar a página."}

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
        """Extrai conteúdo principal com fallbacks para SPAs, formulários e OCR."""
        if not self._page: return "O browser não está aberto."
        try:
            res = self._page.evaluate("""() => {
                const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                };
                const isNoise = (el) => !!el.closest('nav, footer, header, aside, script, style, noscript, [aria-hidden="true"], .ads, #ads, .menu, .sidebar');
                const title = document.title || 'Sem título';
                const allLinks = Array.from(document.querySelectorAll('a')).filter(visible).length;
                const roots = Array.from(document.querySelectorAll('article, main, [role="main"], .content, .post-body, #content')).filter(visible);
                const rootList = roots.length ? roots : [document.body];
                let blocosA = [];
                for (const root of rootList) {
                    blocosA.push(...Array.from(root.querySelectorAll('p, article, section')).filter(el => visible(el) && !isNoise(el)).map(el => clean(el.innerText)).filter(t => t.length > 30));
                }
                blocosA = Array.from(new Set(blocosA)).slice(0, 6);
                const folhas = Array.from(document.body.querySelectorAll('body *')).filter(el => {
                    if (!visible(el) || isNoise(el)) return false;
                    if (Array.from(el.children).some(child => visible(child) && clean(child.innerText).length > 0)) return false;
                    return clean(el.innerText).length > 15;
                }).map(el => {
                    const rect = el.getBoundingClientRect();
                    return {texto: clean(el.innerText), area: Math.round(rect.width * rect.height)};
                }).sort((a, b) => b.area - a.area);
                const blocosB = Array.from(new Set(folhas.map(x => x.texto))).slice(0, 10);
                const forms = Array.from(document.querySelectorAll('form')).filter(visible);
                const campos = Array.from(document.querySelectorAll('input:not([type="hidden"]), textarea, [role="textbox"]')).filter(visible).map(el => ({
                    tipo: el.getAttribute('type') || el.tagName.toLowerCase(),
                    label: clean(el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || el.id || '')
                }));
                const temBlocoLongo = blocosA.concat(blocosB).some(t => t.length >= 80);
                const pareceFormulario = forms.length > 0 && campos.length > 0 && campos.length <= 6 && !temBlocoLongo;
                return {title, allLinks, blocosA, blocosB, forms: forms.length, campos, pareceFormulario};
            }""")

            title = res.get("title") or "Sem título"
            if res.get("pareceFormulario"):
                campos = res.get("campos", [])
                nomes = [c.get("label") or c.get("tipo") or "campo" for c in campos]
                tem_password = any((c.get("tipo") or "").lower() == "password" for c in campos)
                tipo = "formulário de login" if tem_password else "formulário ou página de pesquisa"
                return f"Título da página: {title}. Esta parece ser uma página de {tipo}, com {len(campos)} campo(s): {', '.join(nomes[:5])}."

            estrategia = "A"
            blocos = res.get("blocosA") or []
            texto_util = " ".join(blocos)
            if len(texto_util) < 50:
                estrategia = "B"
                blocos = res.get("blocosB") or []
                texto_util = " ".join(blocos)

            if len(texto_util) >= 50:
                summary = f"Título da página: {title}.\n"
                summary += f"Conteúdo encontrado pela estratégia {estrategia}. A página tem cerca de {res.get('allLinks', 0)} links visíveis.\n"
                for bloco in blocos[:5]:
                    summary += (bloco[:500] + ("..." if len(bloco) > 500 else "")) + "\n"
                self._registar_memoria("leitura", title, {"estrategia": estrategia})
                return summary.strip()

            try:
                from core.vision import Vision
                img_bytes = self.tirar_screenshot()
                if img_bytes:
                    texto_ocr = Vision().extrair_texto_de_bytes(img_bytes).strip()
                    if len(texto_ocr) >= 50:
                        self._registar_memoria("leitura", title, {"estrategia": "OCR"})
                        return f"Título da página: {title}. Conteúdo lido por OCR:\n{texto_ocr[:1800]}"
            except Exception as e:
                console.print(f"[dim red]Fallback OCR falhou: {e}[/dim red]")

            return "Esta página parece não ter texto legível; pode ser uma imagem, vídeo, canvas ou conteúdo bloqueado. Queres que descreva os elementos visuais ou tente outra abordagem?"
        except Exception as e:
            console.print(f"[red]Erro ao extrair conteúdo principal: {e}[/red]")
            return f"Não consegui ler a página por um erro técnico específico: {e}"

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
        """Extrai cabeçalhos visíveis e ancora-os para navegação estrutural por texto."""
        if not self._page: return {"erro": "browser não iniciado"}
        try:
            cabecalhos = self._page.evaluate("""() => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                };
                return Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'))
                    .filter(visible)
                    .map((el, index) => {
                        const id = 'h-' + (index + 1);
                        el.setAttribute('data-neteye-heading-id', id);
                        return {
                            id,
                            nivel: Number(el.tagName.substring(1)),
                            tag: el.tagName.toLowerCase(),
                            texto: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim()
                        };
                    }).filter(item => item.texto.length > 0);
            }""")
            for h in cabecalhos[:10]:
                self._registar_memoria("cabecalho", h.get("texto", ""), {"nivel": h.get("nivel")})
            secoes = [h["texto"] for h in cabecalhos[:8]]
            resumo = "Não encontrei cabeçalhos visíveis nesta página."
            if secoes:
                resumo = f"Esta página tem {len(cabecalhos)} cabeçalhos. Secções principais: {', '.join(secoes)}."
            return {"sucesso": True, "cabecalhos": cabecalhos, "resumo": resumo}
        except Exception as e:
            return {"sucesso": False, "erro": str(e)}

    def obter_elementos_interativos(self, pagina: int = 1, inicio: int | None = None) -> dict:
        """Lista elementos interativos visíveis, injeta data-neteye-id e pagina em lotes de 40."""
        if not self._page: return {"erro": "browser não iniciado"}
        try:
            pagina = max(1, int(pagina or 1))
        except Exception:
            pagina = 1
        offset = int(inicio) if inicio is not None else (pagina - 1) * 40
        try:
            res = self._page.evaluate("""(offset) => {
                const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                };
                const labelFor = (el) => {
                    const id = el.id;
                    const labels = [];
                    if (id) {
                        const explicit = document.querySelector('label[for="' + CSS.escape(id) + '"]');
                        if (explicit) labels.push(clean(explicit.innerText));
                    }
                    const wrapping = el.closest('label');
                    if (wrapping) labels.push(clean(wrapping.innerText));
                    labels.push(clean(el.getAttribute('aria-label')));
                    labels.push(clean(el.getAttribute('placeholder')));
                    labels.push(clean(el.getAttribute('name')));
                    labels.push(clean(el.getAttribute('title')));
                    labels.push(clean(el.value));
                    labels.push(clean(el.innerText || el.textContent));
                    return labels.find(Boolean) || el.tagName.toLowerCase();
                };
                document.querySelectorAll('[data-neteye-id]').forEach(el => el.removeAttribute('data-neteye-id'));
                const selector = [
                    'a[href]', 'button', '[role="button"]', '[role="link"]', '[tabindex]:not([tabindex="-1"])',
                    'input:not([type="hidden"])', 'textarea', 'select', '[role="textbox"]',
                    'input[type="button"]', 'input[type="submit"]'
                ].join(',');
                const seen = new Set();
                const all = [];
                for (const el of Array.from(document.querySelectorAll(selector))) {
                    if (!visible(el) || seen.has(el)) continue;
                    seen.add(el);
                    const tag = el.tagName.toLowerCase();
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    const type = (el.getAttribute('type') || '').toLowerCase();
                    const isTextField = tag === 'textarea' || role === 'textbox' || (tag === 'input' && !['button','submit','reset','checkbox','radio','file','image','range','color','hidden'].includes(type));
                    const label = labelFor(el);
                    if (!label && tag !== 'select') continue;
                    const id = String(all.length + 1);
                    el.setAttribute('data-neteye-id', id);
                    all.push({
                        id: Number(id),
                        tipo: isTextField ? 'campo de texto' : 'elemento clicável',
                        tag, role, input_type: type,
                        texto: label.slice(0, 180)
                    });
                }
                return {total: all.length, lote: all.slice(offset, offset + 40), proximo_inicio: offset + 40 < all.length ? offset + 40 : null};
            }""", offset)
            elementos = res.get("lote", [])
            campos = [e for e in elementos if e.get("tipo") == "campo de texto"]
            clicaveis = [e for e in elementos if e.get("tipo") != "campo de texto"]
            self._elementos_mapeados = {str(e["id"]): e for e in elementos}
            for e in elementos[:10]:
                self._registar_memoria(e.get("tipo", "elemento"), e.get("texto", ""), {"id": e.get("id")})
            return {
                "sucesso": True,
                "pagina": pagina,
                "inicio": offset,
                "total": res.get("total", 0),
                "proximo_inicio": res.get("proximo_inicio"),
                "tem_mais": res.get("proximo_inicio") is not None,
                "campos_de_texto": campos,
                "elementos_clicaveis": clicaveis,
                "elementos": elementos
            }
        except Exception as e:
            console.print(f"[red]Erro ao obter elementos interativos: {e}[/red]")
            return {"sucesso": False, "erro": str(e)}

    def ir_para_cabecalho(self, alvo: str) -> dict:
        """Desloca a página para um cabeçalho por texto, ID, seguinte ou anterior."""
        if not self._page: return {"erro": "browser não iniciado"}
        try:
            antes = self._estado_pagina()
            resultado = self._page.evaluate("""(alvo) => {
                const norm = (s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                };
                const headers = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6')).filter(visible);
                if (!headers.length) return null;
                const wanted = norm(alvo);
                let target = null;
                if (['seguinte', 'baixo', 'próximo', 'proximo'].includes(wanted)) {
                    target = headers.find(h => h.getBoundingClientRect().top > 8);
                } else if (['anterior', 'cima', 'voltar'].includes(wanted)) {
                    target = [...headers].reverse().find(h => h.getBoundingClientRect().top < -8);
                } else {
                    target = headers.find(h => norm(h.getAttribute('data-neteye-heading-id')) === wanted)
                        || headers.find(h => norm(h.innerText || h.textContent).includes(wanted))
                        || headers.find(h => wanted.includes(norm(h.innerText || h.textContent)));
                }
                if (!target) return null;
                target.scrollIntoView({ behavior: 'instant', block: 'start' });
                return {texto: (target.innerText || target.textContent || '').replace(/\s+/g, ' ').trim(), tag: target.tagName.toLowerCase()};
            }""", alvo)
            self._aguardar_pos_acao()
            depois = self._estado_pagina()
            if resultado and self._estado_mudou(antes, depois, aceitar_mesma_pagina=True):
                self._registar_memoria("cabecalho", resultado.get("texto", ""), {"acao": "ir_para_cabecalho"})
                return {"sucesso": True, "cabecalho": resultado.get("texto"), "tag": resultado.get("tag")}
            return {"sucesso": False, "erro": "Não encontrei esse cabeçalho ou a página não se deslocou."}
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
        texto = str(texto or "").strip()
        id_numerico = self._normalizar_id_numerico(texto)

        if id_numerico:
            try:
                el = self._page.locator(f'[data-neteye-id="{id_numerico}"]').first
                if el.count() > 0 and el.is_visible(timeout=800):
                    if self._elemento_e_anuncio(el):
                        return {"sucesso": False, "erro": "Esse elemento parece ser um anúncio; não cliquei sem confirmação explícita."}
                    antes = self._estado_pagina()
                    label = el.evaluate("(node) => (node.innerText || node.getAttribute('aria-label') || node.getAttribute('placeholder') || node.value || '').trim()")
                    el.click(timeout=3000)
                    self._aguardar_pos_acao()
                    depois = self._estado_pagina()
                    if self._estado_mudou(antes, depois, aceitar_mesma_pagina=True):
                        self._registar_memoria("clique", label or f"Elemento {id_numerico}", {"id": id_numerico})
                        return {"sucesso": True, "id": id_numerico, "titulo_pagina": depois.get("titulo"), "url": depois.get("url")}
                    return {"sucesso": False, "erro": "Cliquei no elemento numerado, mas não detetei alteração de URL, DOM ou posição da página."}
            except Exception as e:
                console.print(f"[dim red]clicar por ID falhou ({id_numerico}): {e}[/dim red]")

        texto_escaped = texto.replace("'", "\\'")
        seletores = [
            f"button:has-text('{texto_escaped}'):visible", f"a:has-text('{texto_escaped}'):visible",
            f"[aria-label*='{texto_escaped}' i]:visible", f"[role='button']:has-text('{texto_escaped}'):visible",
            f"[role='link']:has-text('{texto_escaped}'):visible"
        ]
        for s in seletores:
            try:
                el = self._page.locator(s).first
                if el.count() > 0 and el.is_visible(timeout=500):
                    if self._elemento_e_anuncio(el):
                        console.print(f"[dim yellow]Elemento '{texto}' parece ser um anúncio — a ignorar.[/dim yellow]")
                        continue
                    antes = self._estado_pagina()
                    el.click(timeout=3000)
                    self._aguardar_pos_acao()
                    depois = self._estado_pagina()
                    if self._estado_mudou(antes, depois, aceitar_mesma_pagina=True):
                        self._registar_memoria("clique", texto, {"seletor": s})
                        return {"sucesso": True, "titulo_pagina": depois.get("titulo"), "url": depois.get("url")}
                    return {"sucesso": False, "erro": "O clique foi executado, mas não houve alteração detetável no estado da página."}
            except Exception as e:
                console.print(f"[dim red]clicar_elemento falhou ({s}): {e}[/dim red]")
                continue

        res_pos = self._clicar_posicao(texto)
        if res_pos.get("sucesso"):
            self._registar_memoria("clique", texto, {"modo": "posicional"})
            return res_pos
        return {"sucesso": False, "erro": "Não foi possível encontrar ou clicar nesse elemento. Pede a lista de elementos e usa o número anunciado."}

    def escrever_em_campo(self, campo: str, texto: str) -> dict:
        if not self._page: return {"sucesso": False, "erro": "browser não iniciado"}
        campo = str(campo or "").strip()
        texto = str(texto or "")
        id_numerico = self._normalizar_id_numerico(campo)
        try:
            if id_numerico:
                el = self._page.locator(f'[data-neteye-id="{id_numerico}"]').first
                if el.count() > 0 and el.is_visible(timeout=800):
                    antes = self._estado_pagina()
                    el.click(timeout=1500)
                    el.fill(texto)
                    self._aguardar_pos_acao()
                    depois = self._estado_pagina()
                    valor = el.evaluate("node => node.value || node.innerText || ''")
                    if texto in valor or valor == texto:
                        self._registar_memoria("campo", campo, {"id": id_numerico, "preenchido": True})
                        return {"sucesso": True, "campo": campo, "confirmado": True}
                    if self._estado_mudou(antes, depois, aceitar_mesma_pagina=True):
                        return {"sucesso": True, "campo": campo, "confirmado": False, "aviso": "O estado mudou, mas não consegui confirmar o valor final do campo."}
                    return {"sucesso": False, "erro": "Não consegui confirmar que o texto ficou escrito no campo numerado."}

            termo = campo.lower()
            selectors = self._page.locator('input:not([type="hidden"]), textarea, [role="textbox"]').all()
            candidatos = []
            for el in selectors:
                try:
                    if not el.is_visible(timeout=300):
                        continue
                    info = el.evaluate("""(node) => {
                        const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
                        const labels = [];
                        if (node.id) {
                            const lab = document.querySelector('label[for="' + CSS.escape(node.id) + '"]');
                            if (lab) labels.push(clean(lab.innerText));
                        }
                        const wrap = node.closest('label');
                        if (wrap) labels.push(clean(wrap.innerText));
                        return {
                            type: (node.getAttribute('type') || '').toLowerCase(),
                            name: clean(node.getAttribute('name')),
                            id: clean(node.id),
                            placeholder: clean(node.getAttribute('placeholder')),
                            aria: clean(node.getAttribute('aria-label')),
                            labels
                        };
                    }""")
                    haystack = " ".join([info.get("name", ""), info.get("id", ""), info.get("placeholder", ""), info.get("aria", ""), " ".join(info.get("labels", []))]).lower()
                    score = 0
                    if termo and termo in haystack: score += 5
                    for palavra in termo.split():
                        if palavra and palavra in haystack: score += 1
                    if termo in ("palavra-passe", "palavra passe", "password", "senha", "pass") and info.get("type") == "password": score += 10
                    if not termo and info.get("type") in ("text", "search", "email", ""): score += 1
                    candidatos.append((score, el, info))
                except Exception:
                    continue
            candidatos.sort(key=lambda x: x[0], reverse=True)
            if not candidatos or candidatos[0][0] <= 0:
                return {"sucesso": False, "erro": "Não encontrei um campo compatível. Pede a lista de elementos para escolher por número."}
            _, el, info = candidatos[0]
            antes = self._estado_pagina()
            el.click(timeout=1500)
            el.fill(texto)
            self._aguardar_pos_acao()
            depois = self._estado_pagina()
            valor = el.evaluate("node => node.value || node.innerText || ''")
            label = info.get("placeholder") or info.get("aria") or info.get("name") or info.get("id") or campo
            if texto in valor or valor == texto:
                self._registar_memoria("campo", label, {"preenchido": True})
                return {"sucesso": True, "campo": label, "confirmado": True}
            if self._estado_mudou(antes, depois, aceitar_mesma_pagina=True):
                return {"sucesso": True, "campo": label, "confirmado": False, "aviso": "O estado mudou, mas não consegui confirmar o valor final do campo."}
            return {"sucesso": False, "erro": "A escrita não gerou alteração detetável no campo."}
        except Exception as e:
            console.print(f"[red]Erro ao escrever em campo: {e}[/red]")
            return {"sucesso": False, "erro": str(e)}

    def escrever_campo(self, label: str, texto: str) -> dict:
        return self.escrever_em_campo(label or "", texto)

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

    # Valores que a IA pode "inventar" quando não tem a ferramenta certa para o
    # pedido do utilizador (ex: pedir para recarregar/voltar sem essas ferramentas
    # existirem). Nunca devem ser tratados como pesquisa válida — silenciosamente
    # transformar isto numa pesquisa Google confunde um utilizador que não vê o
    # ecrã, pois ele ouve "a pesquisar X" sem perceber que X não fazia sentido.
    _VALORES_INVALIDOS = {
        "about:blank", "about:", "blank", "null", "undefined", "none", "",
        "n/a", "na", "vazio", "nenhum", "nenhuma",
    }

    def _resolver_url(self, alvo: str) -> str | None:
        """
        Resolve um alvo de navegação (URL, atalho ou termo de pesquisa) para um
        URL completo. Retorna None se o alvo for um valor sem sentido — nesse
        caso o chamador (navegar()) deve devolver erro explícito em vez de
        silenciosamente pesquisar algo que não foi pedido pelo utilizador.
        """
        alvo = (alvo or "").strip()
        if alvo.lower() in self._VALORES_INVALIDOS:
            return None
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

                els[idx].click(timeout=3000)

                try:
                    self._page.wait_for_load_state("domcontentloaded", timeout=1500)
                except Exception:
                    pass
                self._page.wait_for_timeout(300)
                self._auto_resolver_interrupcoes()

                # FIX PERFORMANCE: page.content() serializava o DOM inteiro da página
                # (caro em CPU, atrasava o carregamento de vídeo logo após o clique).
                # Comparamos URL (instantâneo) e título da página — muito mais barato
                # que copiar o HTML completo, sem perder a deteção de mudança real.
                url_depois = self._page.url
                titulo_depois = self._obter_titulo_rapido()
                titulo_antes = getattr(self, "_ultimo_titulo_clicar_posicao", None)
                self._ultimo_titulo_clicar_posicao = titulo_depois

                if url_antes != url_depois or titulo_antes != titulo_depois:
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