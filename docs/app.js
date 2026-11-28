// COTA CEA$A — lista de cotações, cards, detalhe com histórico e configurações
// Depende de: util.js, grafico.js, auth.js (carregados antes)

const LS_ANON = 'cc-anon';  // preferências de quem não entrou (favoritos, mercado)

const UNIDADE = { kg: 'R$/kg', dz: 'R$/dúzia', un: 'R$/un' };
const PERIODOS = [
    { rot: '1 mês', dias: 30 },
    { rot: '3 meses', dias: 91 },
    { rot: '1 ano', dias: 365 }
];
const periodosDe = ids => PERIODOS.filter(p => !p.so || ids.every(id => id === p.so));
// cor de cada praça nos gráficos de comparação (boa leitura no fundo claro e no escuro)
const CORES = ['#22c55e', '#3b82f6', '#f97316', '#ec4899', '#a855f7', '#14b8a6', '#FFDF00', '#ef4444'];
const corMercado = id => CORES[Math.max(0, dados.mercados.findIndex(m => m.id === id)) % CORES.length];
const nomeCurto = m => m.nome.replace(/^CEASA\s*-\s*/i, '');
const cidade = id => nomeCurto(mercadoPor(id)).replace(/\s*\([^)]*\)\s*$/, '');   // 'Vitória (ES)' -> 'Vitória'
// nome da cidade na pastilha de preço (favoritos misturam praças)
const etiquetaCidade = (id, extra = '') => `<span class="flex items-start gap-1 text-[10px] font-bold text-slate-300 leading-tight min-w-0 ${extra}"><span class="w-2 h-2 rounded-full shrink-0 mt-px" style="background:${corMercado(id)}"></span><span>${esc(cidade(id))}</span></span>`;

let dados = null;               // { gerado_em, mercados, itens }
let favoritos = [];
let categoriaAtual = 'todos';
let mercadosSel = ['ES'];       // praças marcadas no filtro de local (uma ou mais)
let apenasFavoritos = false;
let periodoDias = 30;           // abre em 1 mês
let det = null;                 // { key, mercs } quando a tela de detalhe está aberta
let scrollLista = 0;

// ---------- preferências (por usuário, ou do aparelho se não houver login) ----------
function salvarPrefs() {
    const p = { favs: favoritos, mercados: mercadosSel, mercado: mercadosSel[0] };
    if (Auth.usuario()) Auth.gravarPrefs(p); else gravarLS(LS_ANON, p);
}
function carregarPrefs() {
    const p = Auth.usuario()
        ? (Auth.lerPrefs() || {})
        : lerLS(LS_ANON, { favs: lerLS('favs_ceasa_v2', []), mercado: lerLS('mercado_ceasa', 'ES') });
    favoritos = Array.isArray(p.favs) ? p.favs : [];
    mercadosSel = Array.isArray(p.mercados) && p.mercados.length ? p.mercados : [p.mercado || 'ES'];
    if (dados) {
        const chaves = new Set(dados.itens.map(i => i.k));
        favoritos = favoritos.filter(k => chaves.has(k));
        mercadosSel = dados.mercados.map(m => m.id).filter(id => mercadosSel.includes(id));   // ordem do site
        if (!mercadosSel.length) mercadosSel = [dados.mercados[0].id];
    }
}
// chamadas pelo auth.js
function aoCriarUsuario() { return { favs: favoritos, mercados: mercadosSel, mercado: mercadosSel[0] }; }
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
    atualizarBotaoMercados();
}

// ---------- dados ----------
// A lista de localidades vem do dados.json: cada CEASA coletada aparece sozinha
// O filtro de local aceita várias praças (caixas de marcar) para comparar preços
function montarMercados() {
    el('pop-mercados').innerHTML = `
        <p class="px-3 pt-2 pb-1 text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Locais (marque um ou mais)</p>
        ${dados.mercados.map(m => `
        <label class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg hover:bg-mata-800 cursor-pointer text-sm text-slate-200">
            <input type="checkbox" value="${esc(m.id)}" onchange="marcarMercado(this)" class="w-4 h-4 accent-[#FFDF00] shrink-0">
            <span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${corMercado(m.id)}"></span>
            <span class="truncate">${esc(m.nome)}</span>
        </label>`).join('')}
        <button onclick="fecharMercados()" class="w-full mt-1 bg-ouro text-mata-950 font-bold rounded-lg py-2 text-sm">Pronto</button>`;
}
function atualizarBotaoMercados() {
    const b = el('btn-mercado-rot');
    if (!b) return;
    const ms = dados ? mercadosSel.map(mercadoPor).filter(Boolean) : [];
    b.textContent = apenasFavoritos ? '📍 Todos os locais'
        : ms.length === 1 ? '📍 ' + nomeCurto(ms[0])
        : ms.length ? '📍 ' + (ms.length <= 3 ? ms.map(m => m.id).join(', ') : `${ms.length} locais`) : '📍 Local';
    el('pop-mercados').querySelectorAll('input').forEach(c => { c.checked = mercadosSel.includes(c.value); });
}
function abrirMercados(ev) {
    ev.stopPropagation();
    if (apenasFavoritos) return;
    atualizarBotaoMercados();
    el('pop-mercados').classList.toggle('hidden');
}
function fecharMercados() { el('pop-mercados').classList.add('hidden'); }
function marcarMercado(cx) {
    const id = cx.value;
    const novo = cx.checked ? [...mercadosSel, id] : mercadosSel.filter(x => x !== id);
    if (!novo.length) { cx.checked = true; return; }   // pelo menos um local
    mercadosSel = dados.mercados.map(m => m.id).filter(x => novo.includes(x));
    salvarPrefs();
    atualizarBotaoMercados();
    renderizarGrid();
}
document.addEventListener('click', (e) => {
    const p = el('pop-mercados');
    if (p && !p.classList.contains('hidden') && !p.contains(e.target)) fecharMercados();
});

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
// Frescor do dado: o app não pode deixar um preço antigo parecer o de hoje.
//  velho      = a última cotação do item não está entre os 3 últimos boletins do mercado (lista esmaecida)
//  muitoVelho = mais de 30 dias antes do boletim mais recente (some da lista; só na busca ou nos favoritos)
const DIAS_LISTA = 30;
function frescor(it, mid) {
    const m = mercadoPor(mid), dt = it.m[mid].dt || m.data;
    return { dt, velho: !m.datas.slice(-3).includes(dt), muitoVelho: dt < somarDias(m.data, -DIAS_LISTA) };
}

function variacao(it, mid) {   // variação em relação à cotação anterior
    const pts = serie(it, mid), n = pts.length;
    const l = it.m[mid].com, a = n > 1 ? pts[n - 2].v : null;
    return { l, a, c: a ? (l - a) / a * 100 : null, pts };
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
    // nos favoritos valem todas as praças, sem filtro de grupo ou local (só a busca por texto)
    const ms = apenasFavoritos ? dados.mercados.map(m => m.id) : mercadosSel;

    const filtrados = dados.itens.filter(i => {
        if (apenasFavoritos) return favoritos.includes(i.k) && casaBusca(i, busca);
        const em = ms.filter(id => i.m[id]);
        if (!em.length) return false;
        if (categoriaAtual !== 'todos' && i.g !== categoriaAtual) return false;
        if (!busca && !favoritos.includes(i.k) && em.every(id => frescor(i, id).muitoVelho)) return false;   // dado velho demais
        return casaBusca(i, busca);
    });

    const merc = ms.map(mercadoPor);
    el('info-boletim').innerHTML = `<i class="fa-regular fa-calendar mr-1 text-ouro ico-campo"></i>` + (merc.length === 1
        ? `Cotação de <strong class="text-slate-200">${dataBR(merc[0].data, true)}</strong>`
        : `Cotações: ${merc.map(m => `<strong class="text-slate-200">${m.id}</strong> ${dataCurta(m.data)}`).join(' · ')}`);
    el('filtros-lista').classList.toggle('hidden', apenasFavoritos);   // grupo e local não valem nos favoritos
    atualizarBotaoMercados();
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
    // várias praças (marcadas ou nos favoritos): cada pastilha de preço diz a cidade
    const comLocal = apenasFavoritos || ms.length > 1;
    filtrados.forEach(i => frag.appendChild(criarCard(i, ms.filter(id => i.m[id]), comLocal)));
    grid.appendChild(frag);
}

const ESTRELA = (cheia, tam = 'w-6 h-6') => `<svg viewBox="0 0 24 24" class="${tam}" fill="${cheia ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 2.5l2.9 6.1 6.6.9-4.8 4.6 1.2 6.6L12 17.5l-5.9 3.2 1.2-6.6L2.5 9.5l6.6-.9z"/></svg>`;

// Mais de uma praça: um bloco de preço por praça, para comparar
function criarCardMulti(item, ids, comLocal) {
    const isFav = favoritos.includes(item.k);
    const detalhe = item.d.replace(/\bLonga Vida\b/g, 'LV');
    const apoio = [UNIDADE[item.u], item.e !== 'kg' ? esc(item.e) : ''].filter(Boolean).join(' · ');
    const blocos = ids.map(id => {
        const c = item.m[id], m = mercadoPor(id), fr = frescor(item, id), { c: vp } = variacao(item, id);
        const data = c.dt && c.dt !== m.data ? `<span class="text-ouro text-[10px] font-bold ml-1"><i class="fa-regular fa-clock"></i> ${dataCurta(c.dt)}</span>` : '';
        return `<div class="bg-mata-950 border border-mata-800 rounded-lg px-2 py-1.5 min-w-0 ${fr.velho ? 'opacity-60' : ''}">
            ${comLocal
                ? etiquetaCidade(id) + (data ? `<span class="block -ml-1 leading-tight">${data}</span>` : '')
                : `<span class="text-[11px] font-bold text-slate-300 flex items-center gap-1 whitespace-nowrap"><span class="w-2 h-2 rounded-full shrink-0" style="background:${corMercado(id)}"></span>${esc(id)}${data}</span>`}
            <span class="block text-[15px] font-bold whitespace-nowrap leading-tight mt-0.5 ${fr.velho ? 'text-slate-500' : 'text-verde-claro'}">R$ ${preco(c.com)}</span>${varMini(vp)}
        </div>`;
    }).join('');
    const card = document.createElement('div');
    card.dataset.act = 'abrir';
    card.dataset.arg = item.k;
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', `Ver histórico de ${item.p} ${item.d}`);
    card.className = 'bg-mata-900 border border-mata-800 rounded-xl pl-1.5 pr-3 py-2 flex items-start gap-2 hover:border-verde/60 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-ouro';
    card.innerHTML = `
        <button data-act="fav" data-arg="${esc(item.k)}" aria-pressed="${isFav}" aria-label="${isFav ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}" class="${isFav ? 'text-ouro' : 'text-ouro/70 hover:text-ouro'} transition-colors p-2 shrink-0">${ESTRELA(isFav, 'w-5 h-5')}</button>
        <div class="min-w-0 flex-1 pt-1">
            <h3 class="font-bold text-white text-[15px] leading-tight">${esc(item.p)}${detalhe ? ` <span class="font-semibold text-slate-300">${esc(detalhe)}</span>` : ''}</h3>
            <p class="text-[11px] text-slate-400 mt-0.5 leading-snug">${apoio}</p>
            <div class="grid grid-cols-3 gap-1.5 mt-2">${blocos}</div>
        </div>`;
    return card;
}
// variação compacta (texto colorido, sem fundo) para os blocos por praça
function varMini(c) {
    if (c == null || !isFinite(c)) return '';
    const k = c > 0.05 ? 'up' : c < -0.05 ? 'dn' : 'fl';
    const cls = { up: 'text-verde-claro', dn: 'text-rose-400', fl: 'text-slate-400' }[k];
    return `<span class="block text-[10px] font-bold leading-tight ${cls}">${k === 'up' ? '▲ +' : k === 'dn' ? '▼ −' : '■ '}${Math.abs(c).toFixed(1).replace('.', ',')}%</span>`;
}

function criarCard(item, ids, comLocal) {
    if (ids.length > 1) return criarCardMulti(item, ids, comLocal);
    const mid = ids[0], mercado = mercadoPor(mid);
    const c = item.m[mid];
    const { c: varPct, pts } = variacao(item, mid);
    const isFav = favoritos.includes(item.k);
    const detalhe = item.d.replace(/\bLonga Vida\b/g, 'LV');   // abreviação para caber na linha
    const sit = c.s;
    const fr = frescor(item, mid), velho = fr.velho;
    const tom = velho ? 'text-slate-500' : sit === 'firme' ? 'text-verde-claro' : sit === 'fraco' ? 'text-rose-400' : 'text-slate-400';
    // linha de apoio: unidade · embalagem · situação do mercado · (cotação antiga)
    const apoio = [
        UNIDADE[item.u],
        item.e !== 'kg' ? esc(item.e) : '',
        sit ? `<span class="${tom} font-semibold">${esc(sit)}</span>` : '',
        c.dt && c.dt !== mercado.data
            ? `<span class="${velho ? 'text-ouro font-extrabold' : 'text-ouro/90'}"><i class="fa-regular fa-clock"></i> ${c.dt.slice(0, 4) === mercado.data.slice(0, 4) ? dataCurta(c.dt) : dataBR(c.dt)}</span>` : ''
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
            <h3 class="font-bold ${velho ? 'text-slate-400' : 'text-white'} text-[15px] leading-tight">${esc(item.p)}${detalhe ? ` <span class="font-semibold ${velho ? 'text-slate-500' : 'text-slate-300'}">${esc(detalhe)}</span>` : ''}</h3>
            <p class="text-[11px] ${velho ? 'text-slate-500' : 'text-slate-400'} mt-0.5 leading-snug">${apoio}</p>
        </div>
        ${Graf.mini(pts.slice(-22).map(p => p.v), velho)}
        <div class="text-right shrink-0 min-w-[78px]">
            ${comLocal ? etiquetaCidade(mid, 'justify-end mb-1') : ''}
            <div class="text-lg font-bold ${velho ? 'text-slate-500' : 'text-verde-claro'} leading-none">R$ ${preco(c.com)}</div>
            <div class="mt-1 ${velho ? 'opacity-50' : ''}">${chipVar(varPct)}</div>
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
    // abre com as mesmas praças mostradas no card (nos favoritos: todas as que têm o produto)
    const todas = dados.mercados.map(m => m.id).filter(id => it.m[id]);
    let mercs = apenasFavoritos ? todas : mercadosSel.filter(id => it.m[id]);
    if (!mercs.length) mercs = todas.slice(0, 1);
    scrollLista = window.scrollY;
    Graf.zoomH = null;
    det = { key, mercs };
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
window.addEventListener('popstate', () => {
    if (!det) return;
    if (det.anual) fecharAnual(); else fecharDetalhe();   // análise anual -> volta ao detalhe
});

// Botões de praça do detalhe: marcar/desmarcar para incluir no gráfico de comparação
function botoesPracas(it) {
    // produto de uma praça só: o cabeçalho já diz qual é, o botão sobraria
    if (dados.mercados.filter(x => it.m[x.id]).length < 2) return '';
    return `<div class="flex flex-wrap gap-1.5 bg-mata-900 border border-mata-800 rounded-2xl p-1.5" role="group" aria-label="Praças no gráfico">
        ${dados.mercados.filter(x => it.m[x.id]).map(x => {
            const on = det.mercs.includes(x.id);
            return `<button data-act="merc" data-arg="${x.id}" aria-pressed="${on}" title="${esc(x.nome)}" class="flex-1 basis-[22%] py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center justify-center gap-1.5 ${on ? 'bg-ouro text-mata-950' : 'text-slate-300 hover:bg-mata-800'}"><span class="w-2.5 h-2.5 rounded-full" style="background:${corMercado(x.id)}"></span>${x.id}</button>`;
        }).join('')}
    </div>
    ${Object.keys(it.m).length > 1 ? '<p class="text-xs text-slate-500 -mt-2 px-1">Toque nas praças para comparar no gráfico.</p>' : ''}`;
}
function botoesPeriodo(pers, per) {
    return `<div class="flex flex-wrap gap-1.5" role="group" aria-label="Período do gráfico">
            ${pers.map(p => `<button data-act="per" data-arg="${p.dias}" aria-pressed="${p === per}" class="flex-none px-2.5 py-1.5 rounded-full text-xs font-semibold border whitespace-nowrap transition-colors ${p === per ? 'bg-ouro text-mata-950 border-ouro' : 'bg-mata-900 text-slate-300 border-mata-700 hover:border-verde/60'}">${p.rot}</button>`).join('')}
            <button data-act="mais" class="flex-none px-2.5 py-1.5 rounded-full text-xs font-semibold botao-ouro whitespace-nowrap transition-colors"><i class="fa-solid fa-lock mr-1 text-[10px]"></i>Mais dados sob consulta</button>
        </div>`;
}

function renderDetalhe() {
    if (det.mercs.length > 1) return renderDetalheMulti();
    const y = window.scrollY;
    const it = itemPorChave(det.key), mid = det.mercs[0], m = it.m[mid], merc = mercadoPor(mid);
    const { a, c, pts } = variacao(it, mid);
    const pers = periodosDe([mid]);
    const per = pers.find(p => p.dias === periodoDias) || pers[0];
    const ultimo = pts[pts.length - 1].d;
    let w = per.dias ? pts.filter(p => p.d >= somarDias(ultimo, -per.dias)) : pts;
    if (w.length < 2) w = pts.slice(-2);
    const vals = w.map(p => p.v);
    const mn = Math.min(...vals), mx = Math.max(...vals), md = vals.reduce((s, v) => s + v, 0) / vals.length;
    const fav = favoritos.includes(it.k);
    const detalhe = it.d.replace(/\bLonga Vida\b/g, 'LV');
    const sub = [merc.nome, it.e !== 'kg' ? it.e : ''].filter(Boolean).join(' · ');
    const box = 'bg-mata-900 border border-mata-800 rounded-2xl p-4';
    const fr = frescor(it, mid);

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

        ${botoesPracas(it)}

        <div>
            <div class="flex items-baseline gap-2"><span class="text-5xl font-bold text-verde-claro leading-none">${R$(m.com)}</span><span class="text-slate-400">${UNIDADE[it.u].replace('R$', '')}</span></div>
            <div class="mt-2 flex items-center gap-2 flex-wrap">${chipVar(c)}${a ? `<span class="text-sm text-slate-400">cotação anterior ${R$(a)}</span>` : ''}</div>
            ${fr.velho ? `<div class="mt-3 bg-ouro/10 text-ouro border border-ouro/30 rounded-xl px-3 py-2.5 text-sm"><i class="fa-solid fa-clock-rotate-left mr-1.5"></i><b>Dado antigo:</b> a última cotação deste item é de ${dataBR(fr.dt, true)}. Pode não refletir o preço de hoje.</div>` : ''}
            ${c != null && Math.abs(c) > 50 ? '<div class="mt-3 bg-ouro/10 text-ouro border border-ouro/30 rounded-xl px-3 py-2.5 text-sm"><i class="fa-solid fa-triangle-exclamation mr-1.5"></i>Variação muito acima do normal. Confira este preço antes de decidir.</div>' : ''}
        </div>

        ${botoesPeriodo(pers, per)}

        <div class="${box}">
            ${Graf.historico('um', w)}
            <p class="text-xs text-slate-500 mt-1">Passe o cursor ou deslize o dedo no gráfico para ver cada dia. Linha amarela tracejada: preço mais recente.</p>
        </div>

        <div class="${box}">
            <table class="w-full text-[15px]">
                <tr><td class="py-2.5 text-slate-300">Menor preço comum (${per.rot.toLowerCase()})</td><td class="text-right font-bold text-white">${R$(mn)}</td></tr>
                <tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">Maior preço comum (${per.rot.toLowerCase()})</td><td class="text-right font-bold text-white">${R$(mx)}</td></tr>
                <tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">Média (${per.rot.toLowerCase()})</td><td class="text-right font-bold text-white">${R$(md)}</td></tr>
                <tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">Mín. – Máx. do dia</td><td class="text-right font-bold text-white">${preco(m.min)} – ${preco(m.max)}</td></tr>
            </table>
        </div>
        <button data-act="anual" class="w-full bg-ouro hover:brightness-95 text-black font-bold rounded-2xl py-3.5 flex items-center justify-center gap-2 shadow-sm transition"><i class="fa-solid fa-chart-line"></i>Análise anualizada e previsão de preços</button>`;
    window.scrollTo(0, y);
}

// Detalhe comparando várias praças: preço atual de cada uma, gráfico com uma linha por praça e tabela
function renderDetalheMulti() {
    const y = window.scrollY;
    const it = itemPorChave(det.key), ids = det.mercs;
    const pers = periodosDe(ids);
    const per = pers.find(p => p.dias === periodoDias) || pers[0];
    const fim = ids.map(id => { const p = serie(it, id); return p[p.length - 1].d; }).sort().pop();
    const ini = somarDias(fim, -per.dias);
    const series = ids.map(id => {
        const pts = serie(it, id);
        let w = pts.filter(p => p.d >= ini);
        if (!w.length) w = pts.slice(-1);
        return { id, cor: corMercado(id), pts: w };
    });
    const fav = favoritos.includes(it.k);
    const detalhe = it.d.replace(/\bLonga Vida\b/g, 'LV');
    const sub = [UNIDADE[it.u], it.e !== 'kg' ? it.e : ''].filter(Boolean).join(' · ');
    const box = 'bg-mata-900 border border-mata-800 rounded-2xl p-4';
    const est = series.map(s => {
        const v = s.pts.map(p => p.v);
        return { mn: Math.min(...v), mx: Math.max(...v), md: v.reduce((a, b) => a + b, 0) / v.length };
    });
    const cab = ids.map(id => `<th class="text-right pb-2 font-bold text-slate-300 text-sm"><span class="inline-flex items-center gap-1"><span class="w-2 h-2 rounded-full" style="background:${corMercado(id)}"></span>${id}</span></th>`).join('');
    const linha = (rot, f, first) => `<tr class="${first ? '' : 'border-t border-mata-800'}"><td class="py-2.5 text-slate-300 pr-2">${rot}</td>${ids.map((id, k) => `<td class="text-right font-bold text-white whitespace-nowrap pl-2">${f(id, k)}</td>`).join('')}</tr>`;
    const r = per.rot.toLowerCase();

    el('vista-detalhe').innerHTML = `
        <div class="flex items-center justify-between">
            <button data-act="voltar" class="text-slate-200 hover:text-white font-semibold py-2 pr-3 -ml-1"><i class="fa-solid fa-arrow-left mr-1.5"></i>Voltar</button>
            <button data-act="fav" data-arg="${esc(it.k)}" aria-pressed="${fav}" aria-label="${fav ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}" class="${fav ? 'text-ouro' : 'text-ouro/70 hover:text-ouro'} p-1">${ESTRELA(fav)}</button>
        </div>

        <div>
            <h2 class="text-2xl font-bold text-white leading-tight">${esc(it.p)}${detalhe ? ` <span class="font-semibold text-slate-300">${esc(detalhe)}</span>` : ''}</h2>
            <p class="text-sm text-slate-400 mt-1">${esc(sub)} · comparando ${ids.length} praças</p>
        </div>

        ${botoesPracas(it)}

        <div class="grid grid-cols-2 gap-2">
            ${ids.map(id => {
                const m = it.m[id], merc = mercadoPor(id), { c } = variacao(it, id), fr = frescor(it, id);
                return `<div class="${box} !p-3 ${fr.velho ? 'opacity-70' : ''}">
                    <p class="text-xs font-semibold text-slate-400 flex items-center gap-1.5 truncate"><span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${corMercado(id)}"></span>${esc(nomeCurto(merc))}</p>
                    <p class="text-2xl font-bold text-verde-claro leading-tight mt-1">${R$(m.com)}</p>
                    <div class="mt-1 flex items-center gap-1.5 flex-wrap">${chipVar(c)}<span class="text-[11px] ${fr.velho ? 'text-ouro font-bold' : 'text-slate-500'}">${dataCurta(fr.dt)}</span></div>
                </div>`;
            }).join('')}
        </div>

        ${botoesPeriodo(pers, per)}

        <div class="${box}">
            ${Graf.historico('multi', series)}
            <p class="text-xs text-slate-500 mt-1">Passe o cursor ou deslize o dedo no gráfico para ver o preço de cada praça no dia.</p>
        </div>

        <div class="${box} overflow-x-auto">
            <table class="w-full text-[15px]">
                <tr><th></th>${cab}</tr>
                ${linha(`Menor (${r})`, (id, k) => preco(est[k].mn), true)}
                ${linha(`Maior (${r})`, (id, k) => preco(est[k].mx))}
                ${linha(`Média (${r})`, (id, k) => preco(est[k].md))}
                ${linha('Mín. – Máx. do dia', id => `${preco(it.m[id].min)}–${preco(it.m[id].max)}`)}
            </table>
        </div>
        <button data-act="anual" class="w-full bg-ouro hover:brightness-95 text-black font-bold rounded-2xl py-3.5 flex items-center justify-center gap-2 shadow-sm transition"><i class="fa-solid fa-chart-line"></i>Análise anualizada e previsão de preços</button>`;
    window.scrollTo(0, y);
}

// ---------- ações ----------
function toggleFavorito(chave) {
    favoritos = favoritos.includes(chave) ? favoritos.filter(k => k !== chave) : [...favoritos, chave];
    salvarPrefs();
    if (det) (det.anual ? renderAnual : renderDetalhe)(); else { const y = window.scrollY; renderizarGrid(); window.scrollTo(0, y); }
}
function toggleFiltroFavoritos() {
    fecharMercados();
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
// detalhe: inclui/retira uma praça do gráfico (sempre fica pelo menos uma)
function alternarPracaDetalhe(id) {
    const on = det.mercs.includes(id);
    if (on && det.mercs.length === 1) return;
    const novo = on ? det.mercs.filter(x => x !== id) : [...det.mercs, id];
    det.mercs = dados.mercados.map(m => m.id).filter(x => novo.includes(x));
    renderDetalhe();
}
function filtrarProdutos() { renderizarGrid(); }

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
        case 'merc': Graf.zoomH = null; alternarPracaDetalhe(arg); break;
        case 'anual': abrirAnual(); break;
        case 'anual-merc': det.anual.mid = arg; ANUAL.zoom = null; renderAnual(); break;
        case 'anual-ano': alternarAnoAnual(arg); break;
        case 'mais': abrirFolha(`
            <div class="p-6 pt-16 text-center">
                <div class="bg-mata-900 border border-ouro/40 rounded-2xl p-6">
                    <i class="fa-solid fa-chart-line text-ouro text-3xl mb-3"></i>
                    <h3 class="text-xl font-bold text-white mb-2">Mais dados sob consulta</h3>
                    <p class="text-slate-300 leading-relaxed">Para mais dados e análises, entre em contato pelo email <a href="mailto:cota.ceasa@gmail.com" class="botao-ouro font-semibold break-all">cota.ceasa@gmail.com</a></p>
                    <button onclick="fecharFolha()" class="mt-5 w-full bg-ouro text-mata-950 font-bold py-3 rounded-xl">Fechar</button>
                </div>
            </div>`); break;
        case 'per': periodoDias = +arg; Graf.zoomH = null; renderDetalhe(); break;
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
