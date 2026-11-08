// COTA CEA$A — lista de cotações, cards, detalhe com histórico e configurações
// Depende de: util.js, grafico.js, auth.js (carregados antes)

const LS_ANON = 'cc-anon';  // preferências de quem não entrou (favoritos, mercado, previsão)

const UNIDADE = { kg: 'R$/kg', dz: 'R$/dúzia', un: 'R$/un' };
const PERIODOS = [
    { rot: '7 dias', dias: 7 },
    { rot: '15 dias', dias: 15 },
    { rot: '1 mês', dias: 30 },
    { rot: 'Tudo', dias: null }
];

let dados = null;               // { gerado_em, mercados, itens }
let favoritos = [];
let categoriaAtual = 'todos';
let mercadoAtual = 'ES';
let apenasFavoritos = false;
let previsaoOn = true;
let periodoIdx = 3;
let det = null;                 // { key } quando a tela de detalhe está aberta
let scrollLista = 0;

// ---------- preferências (por usuário, ou do aparelho se não houver login) ----------
function salvarPrefs() {
    const p = { favs: favoritos, mercado: mercadoAtual, prev: previsaoOn };
    if (Auth.usuario()) Auth.gravarPrefs(p); else gravarLS(LS_ANON, p);
}
function carregarPrefs() {
    const p = Auth.usuario()
        ? (Auth.lerPrefs() || {})
        : lerLS(LS_ANON, { favs: lerLS('favs_ceasa_v2', []), mercado: lerLS('mercado_ceasa', 'ES') });
    favoritos = Array.isArray(p.favs) ? p.favs : [];
    mercadoAtual = p.mercado || 'ES';
    previsaoOn = p.prev !== false;
    if (dados) {
        const chaves = new Set(dados.itens.map(i => i.k));
        favoritos = favoritos.filter(k => chaves.has(k));
        if (!dados.mercados.some(m => m.id === mercadoAtual)) mercadoAtual = dados.mercados[0].id;
    }
}
// chamadas pelo auth.js
function aoCriarUsuario() { return { favs: favoritos, mercado: mercadoAtual, prev: previsaoOn }; }
function aoMudarUsuario() {
    carregarPrefs();
    apenasFavoritos = false;
    sincronizarUI();
    if (det) fecharDetalhe(true);
    renderizarGrid();
}

function sincronizarUI() {
    const u = Auth.usuario();
    const b = el('btn-conta');
    b.innerHTML = u
        ? `<span class="font-black text-base leading-none">${esc(u.nome.trim().charAt(0).toUpperCase() || '?')}</span>`
        : '<i class="fa-solid fa-user"></i>';
    b.title = u ? 'Minha conta' : 'Entrar';
    el('select-mercado').value = mercadoAtual;
}

// ---------- dados ----------
// A lista de localidades vem do dados.json: cada CEASA coletada aparece sozinha
function montarMercados() {
    el('select-mercado').innerHTML = dados.mercados
        .map(m => `<option value="${esc(m.id)}">📍 ${esc(m.nome)}</option>`).join('');
}

const mercadoPor = (id) => dados.mercados.find(m => m.id === id);
const itemPorChave = (k) => dados.itens.find(i => i.k === k);

const memo = new Map();
function serie(it, mid) {   // [{d, v}] só com os dias em que o item foi cotado
    const chave = it.k + '#' + mid;
    if (memo.has(chave)) return memo.get(chave);
    const datas = mercadoPor(mid).datas, pts = [];
    it.m[mid].h.forEach((v, i) => { if (v != null) pts.push({ d: datas[i], v }); });
    memo.set(chave, pts);
    return pts;
}
function variacao(it, mid) {   // variação em relação à cotação anterior
    const pts = serie(it, mid), n = pts.length;
    const l = it.m[mid].com, a = n > 1 ? pts[n - 2].v : null;
    return { l, a, c: a ? (l - a) / a * 100 : null, pts };
}
function previsaoDe(pts) {
    const f = Graf.previsao(pts.map(p => p.v), 5);
    if (!f.length) return [];
    const d = Graf.diasUteis(pts[pts.length - 1].d, f.length);
    return f.map((x, i) => ({ ...x, d: d[i] }));
}

async function carregarDados() {
    try {
        const resp = await fetch('dados.json', { cache: 'no-cache' });
        if (!resp.ok) throw new Error(resp.status);
        dados = await resp.json();
        montarMercados();
        carregarPrefs();
        salvarPrefs();
        sincronizarUI();
        renderizarGrid();
    } catch (e) {
        console.error('Falha ao carregar dados.json', e);
        mostrarVazio('<i class="fa-solid fa-triangle-exclamation text-2xl text-ouro mb-3"></i>' +
            '<p class="font-semibold text-slate-200">Não foi possível carregar as cotações.</p>' +
            '<p class="text-sm mt-1">Verifique sua conexão e tente novamente.</p>' +
            '<button onclick="location.reload()" class="mt-4 bg-ouro text-mata-950 font-semibold px-4 py-2 rounded-xl text-sm">Tentar de novo</button>');
        el('info-boletim').textContent = 'Cotações indisponíveis';
    }
}

function mostrarVazio(html) {
    el('grid-produtos').innerHTML = '';
    const v = el('estado-vazio');
    v.innerHTML = html;
    v.classList.remove('hidden');
}

// ---------- lista ----------
// Busca tolerante: ignora acentos e aceita pequenos erros de digitação ("tomte" acha "tomate")
function casaBusca(it, busca) {
    if (!busca) return true;
    const alvo = norm(it.p + ' ' + it.d + ' ' + it.d.replace(/\bLonga Vida\b/g, 'LV'));   // aceita também a abreviação mostrada no card
    const palavras = alvo.split(/[\s\-\/]+/);
    return busca.split(' ').filter(Boolean).every(w => {
        if (alvo.includes(w)) return true;
        const tol = w.length < 4 ? 0 : w.length < 7 ? 1 : 2;
        return tol > 0 && palavras.some(t => distancia(w, t) <= tol || (t.length > w.length && distancia(w, t.slice(0, w.length)) <= tol));
    });
}

function renderizarGrid() {
    if (!dados) return;
    const grid = el('grid-produtos');
    const busca = norm(el('input-busca').value.trim());
    const mercado = mercadoPor(mercadoAtual);

    const filtrados = dados.itens.filter(i => {
        if (!i.m[mercadoAtual]) return false;
        if (apenasFavoritos && !favoritos.includes(i.k)) return false;
        if (categoriaAtual !== 'todos' && i.g !== categoriaAtual) return false;
        return casaBusca(i, busca);
    });

    el('info-boletim').innerHTML = `<i class="fa-regular fa-calendar mr-1 text-ouro"></i>Cotação de <strong class="text-slate-200">${dataBR(mercado.data, true)}</strong>`;
    el('info-contagem').textContent = `${filtrados.length} ${filtrados.length === 1 ? 'produto' : 'produtos'}`;
    el('fav-count-badge').textContent = favoritos.length;
    const btnFav = el('btn-fav-header');
    btnFav.setAttribute('aria-pressed', apenasFavoritos);
    btnFav.classList.toggle('bg-ouro', apenasFavoritos);
    btnFav.classList.toggle('text-mata-950', apenasFavoritos);
    btnFav.classList.toggle('bg-mata-800', !apenasFavoritos);
    btnFav.classList.toggle('text-ouro', !apenasFavoritos);
    el('ico-fav-header').setAttribute('fill', apenasFavoritos ? 'currentColor' : 'none');
    el('chip-fav').classList.toggle('hidden', !apenasFavoritos);
    el('chip-fav').classList.toggle('inline-flex', apenasFavoritos);

    grid.innerHTML = '';
    if (!filtrados.length) {
        mostrarVazio(apenasFavoritos && !favoritos.length
            ? '<i class="fa-regular fa-star text-2xl text-ouro mb-3"></i><p class="font-semibold text-slate-200">Você ainda não tem favoritos.</p><p class="text-sm mt-1">Toque na estrela de um produto para acompanhá-lo aqui.</p>'
            : '<i class="fa-solid fa-magnifying-glass text-2xl mb-3"></i><p class="font-semibold text-slate-200">Nenhum produto encontrado.</p><p class="text-sm mt-1">Tente outro termo ou tipo de produto.</p>');
        return;
    }
    el('estado-vazio').classList.add('hidden');

    const frag = document.createDocumentFragment();
    filtrados.forEach(i => frag.appendChild(criarCard(i, mercado)));
    grid.appendChild(frag);
}

const ESTRELA = (cheia, tam = 'w-6 h-6') => `<svg viewBox="0 0 24 24" class="${tam}" fill="${cheia ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 2.5l2.9 6.1 6.6.9-4.8 4.6 1.2 6.6L12 17.5l-5.9 3.2 1.2-6.6L2.5 9.5l6.6-.9z"/></svg>`;

function criarCard(item, mercado) {
    const c = item.m[mercadoAtual];
    const { c: varPct, pts } = variacao(item, mercadoAtual);
    const isFav = favoritos.includes(item.k);
    const detalhe = item.d.replace(/\bLonga Vida\b/g, 'LV');   // abreviação para caber na linha
    const sit = c.s;
    const tom = sit === 'firme' ? 'text-verde-claro' : sit === 'fraco' ? 'text-rose-400' : 'text-slate-400';
    // linha de apoio: unidade · embalagem · situação do mercado · (cotação antiga)
    const apoio = [
        UNIDADE[item.u],
        item.e !== 'kg' ? esc(item.e) : '',
        sit ? `<span class="${tom} font-semibold">${esc(sit)}</span>` : '',
        c.dt && c.dt !== mercado.data ? `<span class="text-ouro/90"><i class="fa-regular fa-clock"></i> ${dataCurta(c.dt)}</span>` : ''
    ].filter(Boolean).join(' · ');

    const card = document.createElement('div');
    card.dataset.act = 'abrir';
    card.dataset.arg = item.k;
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', `Ver histórico de ${item.p} ${item.d}`);
    card.className = 'bg-mata-900 border border-mata-800 rounded-xl pl-1.5 pr-3 py-2 flex items-center gap-2 hover:border-verde/60 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-ouro';
    card.innerHTML = `
        <button data-act="fav" data-arg="${esc(item.k)}" aria-pressed="${isFav}" aria-label="${isFav ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}" class="${isFav ? 'text-ouro' : 'text-ouro/70 hover:text-ouro'} transition-colors p-2 shrink-0">${ESTRELA(isFav, 'w-5 h-5')}</button>
        <div class="min-w-0 flex-1">
            <h3 class="font-bold text-white text-[15px] leading-tight">${esc(item.p)}${detalhe ? ` <span class="font-semibold text-slate-300">${esc(detalhe)}</span>` : ''}</h3>
            <p class="text-[11px] text-slate-400 mt-0.5 leading-snug">${apoio}</p>
        </div>
        ${Graf.mini(pts.slice(-22).map(p => p.v))}
        <div class="text-right shrink-0 min-w-[78px]">
            <div class="text-lg font-bold text-verde-claro leading-none">R$ ${preco(c.com)}</div>
            <div class="mt-1">${chipVar(varPct)}</div>
        </div>`;
    return card;
}

// ---------- detalhe (histórico no tempo) ----------
function mostrarVista(qual) {
    el('vista-lista').classList.toggle('hidden', qual !== 'lista');
    el('vista-detalhe').classList.toggle('hidden', qual !== 'detalhe');
}

function abrirDetalhe(key) {
    const it = itemPorChave(key);
    if (!it) return;
    if (!it.m[mercadoAtual]) mercadoAtual = Object.keys(it.m)[0];
    scrollLista = window.scrollY;
    det = { key };
    history.pushState({ det: key }, '');
    mostrarVista('detalhe');
    renderDetalhe();
    window.scrollTo(0, 0);
}
function fecharDetalhe(semScroll) {
    det = null;
    mostrarVista('lista');
    if (!semScroll) { renderizarGrid(); window.scrollTo(0, scrollLista); }
}
function voltar() {
    if (history.state && history.state.det) history.back(); else fecharDetalhe();
}
window.addEventListener('popstate', () => { if (det) fecharDetalhe(); });

function renderDetalhe() {
    const y = window.scrollY;
    const it = itemPorChave(det.key), mid = mercadoAtual, m = it.m[mid], merc = mercadoPor(mid);
    const { a, c, pts } = variacao(it, mid);
    const per = PERIODOS[periodoIdx];
    const ultimo = pts[pts.length - 1].d;
    let w = per.dias ? pts.filter(p => p.d >= somarDias(ultimo, -per.dias)) : pts;
    if (w.length < 2) w = pts.slice(-2);
    const vals = w.map(p => p.v);
    const mn = Math.min(...vals), mx = Math.max(...vals), md = vals.reduce((s, v) => s + v, 0) / vals.length;
    const fc = previsaoOn ? previsaoDe(pts) : [];
    const fav = favoritos.includes(it.k);
    const detalhe = it.d.replace(/\bLonga Vida\b/g, 'LV');
    const sub = [merc.nome, it.e !== 'kg' ? it.e : ''].filter(Boolean).join(' · ');
    const box = 'bg-mata-900 border border-mata-800 rounded-2xl p-4';

    el('vista-detalhe').innerHTML = `
        <div class="flex items-center justify-between">
            <button data-act="voltar" class="text-slate-200 hover:text-white font-semibold py-2 pr-3 -ml-1"><i class="fa-solid fa-arrow-left mr-1.5"></i>Voltar</button>
            <button data-act="fav" data-arg="${esc(it.k)}" aria-pressed="${fav}" aria-label="${fav ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}" class="${fav ? 'text-ouro' : 'text-ouro/70 hover:text-ouro'} p-1">${ESTRELA(fav)}</button>
        </div>

        <div>
            <h2 class="text-2xl font-bold text-white leading-tight">${esc(it.p)}${detalhe ? ` <span class="font-semibold text-slate-300">${esc(detalhe)}</span>` : ''}</h2>
            <p class="text-sm text-slate-400 mt-1">${esc(sub)}</p>
            <p class="text-xs text-slate-500 mt-0.5">Cotação de ${dataBR(merc.data, true)}${m.dt ? ` · última cotação deste item: ${dataBR(m.dt)}` : ''}</p>
        </div>

        <div class="grid grid-cols-3 gap-1.5 bg-mata-900 border border-mata-800 rounded-2xl p-1.5" role="group" aria-label="Localidade">
            ${dados.mercados.filter(x => it.m[x.id]).map(x => `<button data-act="merc" data-arg="${x.id}" class="py-2.5 rounded-xl text-sm font-semibold transition-colors ${x.id === mid ? 'bg-ouro text-mata-950' : 'text-slate-300 hover:bg-mata-800'}">${x.id}</button>`).join('')}
        </div>

        <div>
            <div class="flex items-baseline gap-2"><span class="text-5xl font-bold text-verde-claro leading-none">${R$(m.com)}</span><span class="text-slate-400">${UNIDADE[it.u].replace('R$', '')}</span></div>
            <div class="mt-2 flex items-center gap-2 flex-wrap">${chipVar(c)}${a ? `<span class="text-sm text-slate-400">cotação anterior ${R$(a)}</span>` : ''}</div>
            ${c != null && Math.abs(c) > 50 ? '<div class="mt-3 bg-ouro/10 text-ouro border border-ouro/30 rounded-xl px-3 py-2.5 text-sm"><i class="fa-solid fa-triangle-exclamation mr-1.5"></i>Variação muito acima do normal. Confira este preço antes de decidir.</div>' : ''}
        </div>

        <div class="flex gap-2 overflow-x-auto no-scrollbar" role="group" aria-label="Período do gráfico">
            ${PERIODOS.map((p, i) => `<button data-act="per" data-arg="${i}" aria-pressed="${i === periodoIdx}" class="flex-none px-4 py-2 rounded-full text-sm font-semibold border transition-colors ${i === periodoIdx ? 'bg-ouro text-mata-950 border-ouro' : 'bg-mata-900 text-slate-300 border-mata-700 hover:border-verde/60'}">${p.rot}</button>`).join('')}
        </div>

        <div class="${box}">
            ${Graf.desenhar(w, fc)}
            <p class="text-xs text-slate-500 mt-1">Passe o cursor ou deslize o dedo no gráfico para ver cada dia.${fc.length ? ' Pontilhado amarelo e faixa: previsão (teste).' : ''}</p>
        </div>

        <div class="${box}">
            <div class="flex items-center justify-between">
                <b class="text-lg text-white">Previsão <span class="text-slate-400 font-medium text-sm">(teste)</span></b>
                <button data-act="prev" aria-pressed="${previsaoOn}" class="px-3.5 py-2 rounded-xl text-sm font-semibold border border-mata-700 bg-mata-800 text-slate-200 hover:border-ouro/60">${previsaoOn ? 'Ocultar' : 'Mostrar'}</button>
            </div>
            ${fc.length ? `<table class="w-full mt-2 text-[15px]">${fc.map(x => `<tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">${dataCurta(x.d)}</td><td class="text-slate-400">${preco(x.lo)} – ${preco(x.hi)}</td><td class="text-right font-bold text-white">${R$(x.p)} ${chipVar((x.p - m.com) / m.com * 100)}</td></tr>`).join('')}</table>`
                : previsaoOn ? '<p class="text-sm text-slate-400 mt-2">Histórico curto demais para estimar.</p>' : ''}
            <p class="text-xs text-slate-500 mt-2">Estimativa simples (tendência recente e retorno à média), só para testar o app. Não é recomendação.</p>
        </div>

        <div class="${box}">
            <table class="w-full text-[15px]">
                <tr><td class="py-2.5 text-slate-300">Menor preço comum (${per.rot.toLowerCase()})</td><td class="text-right font-bold text-white">${R$(mn)}</td></tr>
                <tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">Maior preço comum (${per.rot.toLowerCase()})</td><td class="text-right font-bold text-white">${R$(mx)}</td></tr>
                <tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">Média (${per.rot.toLowerCase()})</td><td class="text-right font-bold text-white">${R$(md)}</td></tr>
                <tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">Mín. – Máx. do dia</td><td class="text-right font-bold text-white">${preco(m.min)} – ${preco(m.max)}</td></tr>
            </table>
        </div>`;
    window.scrollTo(0, y);
}

// ---------- ações ----------
function toggleFavorito(chave) {
    favoritos = favoritos.includes(chave) ? favoritos.filter(k => k !== chave) : [...favoritos, chave];
    salvarPrefs();
    if (det) renderDetalhe(); else { const y = window.scrollY; renderizarGrid(); window.scrollTo(0, y); }
}
function toggleFiltroFavoritos() {
    if (det) fecharDetalhe(true);
    apenasFavoritos = !apenasFavoritos;
    renderizarGrid();
}
// Chip "Só favoritos ✕": limpa o filtro de favoritos e também a busca e o tipo de produto
function limparFiltros() {
    apenasFavoritos = false;
    categoriaAtual = 'todos';
    el('select-categoria').value = 'todos';
    el('input-busca').value = '';
    renderizarGrid();
}
function filtrarCategoria(cat) { categoriaAtual = cat; renderizarGrid(); }
function alterarMercado(id) {
    mercadoAtual = id;
    salvarPrefs();
    el('select-mercado').value = id;
    if (det) renderDetalhe(); else renderizarGrid();
}
function filtrarProdutos() { renderizarGrid(); }

function alternarPrevisao() {
    previsaoOn = !previsaoOn;
    salvarPrefs();
    if (det) renderDetalhe(); else renderizarGrid();
}

// ---------- conta e configurações ----------
function abrirModalAuth(aba) {
    if (Auth.usuario()) abrirConfiguracoes(); else Auth.abrir(aba === 'new' ? 'new' : 'in');
}

function abrirConfiguracoes() {
    const u = Auth.usuario();
    const BT = 'w-full font-bold rounded-xl py-3.5 text-base';
    abrirFolha(`
        <div class="flex items-center justify-between px-4 h-14 border-b border-mata-800 bg-mata-900 sticky top-0">
            <span class="font-bold text-white">Configurações</span>
            <button onclick="fecharFolha()" aria-label="Fechar" class="text-slate-400 hover:text-white p-2"><i class="fa-solid fa-xmark text-lg"></i></button>
        </div>
        <div class="px-5 py-6 space-y-5">
            <div class="bg-mata-900 border border-mata-800 rounded-2xl p-4">
                ${u ? `<p class="text-slate-400 text-sm">Conectado como</p>
                       <p class="text-xl font-bold text-white mt-0.5">${esc(u.nome)}</p>
                       <p class="text-sm text-slate-400">${esc(u.id)}</p>
                       <button class="${BT} mt-4 border border-rose-400/40 text-rose-300 hover:bg-rose-500/10" onclick="Auth.sair()">Sair</button>`
                     : `<p class="text-slate-200 font-semibold">Você não está conectado</p>
                       <p class="text-sm text-slate-400 mt-1 mb-4">Entre para guardar seus favoritos e preferências neste aparelho.</p>
                       <button class="${BT} bg-ouro text-mata-950 hover:bg-ouro-escuro" onclick="Auth.abrir('in')">Entrar</button>
                       <button class="w-full text-slate-300 underline py-3 text-sm" onclick="Auth.abrir('new')">Criar um acesso novo</button>`}
            </div>

            <div class="bg-mata-900 border border-mata-800 rounded-2xl p-4 flex items-center justify-between gap-3">
                <div><p class="font-semibold text-white">Mostrar previsão <span class="text-slate-400 font-medium text-sm">(teste)</span></p>
                     <p class="text-sm text-slate-400">Estimativa dos próximos 5 dias úteis nos cards e no gráfico.</p></div>
                <button role="switch" aria-checked="${previsaoOn}" aria-label="Mostrar previsão" onclick="alternarPrevisao();abrirConfiguracoes()" class="relative flex-none w-12 h-7 rounded-full transition-colors ${previsaoOn ? 'bg-verde' : 'bg-mata-700'}">
                    <span class="absolute top-0.5 ${previsaoOn ? 'left-[22px]' : 'left-0.5'} w-6 h-6 rounded-full bg-white transition-all"></span>
                </button>
            </div>

            <p class="text-xs text-slate-500">Dados: boletins diários do CEASA, atualizados em ${dados ? dataBR(dados.gerado_em.slice(0, 10)) : '—'}. Os acessos e favoritos ficam salvos só neste aparelho.</p>
        </div>`);
}

// ---------- eventos ----------
document.addEventListener('click', (e) => {
    const a = e.target.closest('[data-act]');
    if (!a) return;
    const arg = a.dataset.arg;
    switch (a.dataset.act) {
        case 'fav': toggleFavorito(arg); break;
        case 'abrir': abrirDetalhe(arg); break;
        case 'voltar': voltar(); break;
        case 'merc': alterarMercado(arg); break;
        case 'per': periodoIdx = +arg; renderDetalhe(); break;
        case 'prev': alternarPrevisao(); break;
    }
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.dataset && e.target.dataset.act === 'abrir') abrirDetalhe(e.target.dataset.arg);
});

// ---------- inicialização ----------
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(err => console.warn('SW não registrado', err));
}
Auth.restaurar();
carregarPrefs();
sincronizarUI();
carregarDados();
