/* COTA CEA$A — Comparação histórica entre praças (até 5)
 * Abre a partir do detalhe de um produto. Uma linha por praça com o preço comum ao longo do tempo:
 * preço diário (1 e 3 meses) ou média semanal (1 ano). Mesmos períodos do detalhe (até 1 ano);
 * mais que isso, só sob consulta.
 * Abaixo, um quadro por praça com média, menor, maior e última cotação do período.
 * Item cotado numa praça só: avisa e oferece comparar com produtos semelhantes (mesmo produto e
 * mesma unidade de preço, de qualquer tipo/classificação) nas outras praças. Nesse modo, cada outra
 * praça vira uma linha com a média diária de todos os tipos semelhantes dela.
 */
const COMP = {
    MAX: 5,
    get PERIODOS() { return PERIODOS; }   // os mesmos do detalhe do produto (app.js): 1 mês, 3 meses, 1 ano
};

const pracasDoItem = (it) => dados.mercados.map(m => m.id).filter(id => it.m[id]);
const normNome = (t) => (t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();

// Semelhantes do item (que está numa praça só): { praça: [itens] } nas outras praças,
// com o mesmo nome de produto e a mesma unidade de preço (tipos e classificações diferentes entram juntos)
function semelhantesDoItem(it, origem) {
    const nome = normNome(it.p), grupos = {};
    for (const x of dados.itens) {
        if (x === it || x.u !== it.u || normNome(x.p) !== nome) continue;
        for (const id of Object.keys(x.m)) if (id !== origem) (grupos[id] = grupos[id] || []).push(x);
    }
    return grupos;
}
// média diária do preço comum de vários itens numa praça
function serieGrupo(itens, id) {
    const acc = new Map();
    for (const x of itens) for (const { d, v } of serie(x, id)) {
        const a = acc.get(d) || [0, 0];
        a[0] += v; a[1]++;
        acc.set(d, a);
    }
    return [...acc.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([d, [s, n]]) => ({ d, v: s / n }));
}
// série de uma praça na comparação: o próprio item ou, no modo semelhantes, o grupo daquela praça
function serieComp(c, it, id) {
    if (!c.sim || id === c.sim.origem) return serie(it, id);
    return c.sim.cache[id] || (c.sim.cache[id] = serieGrupo(c.sim.grupos[id], id));
}
const pracasComp = (c, it) => c.sim ? c.sim.ids : pracasDoItem(it);

// segunda-feira da semana de uma data ISO
function inicioSemanaISO(d) {
    const t = new Date(d + 'T12:00:00');
    t.setDate(t.getDate() - (t.getDay() + 6) % 7);
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
}
// [{d, v}] diário -> média por semana ou por mês ({d: início do período, v: média})
function agregarComp(pts, porMes) {
    const acc = new Map();
    for (const { d, v } of pts) {
        const k = porMes ? d.slice(0, 7) + '-01' : inicioSemanaISO(d);
        const a = acc.get(k) || [0, 0];
        a[0] += v; a[1]++;
        acc.set(k, a);
    }
    return [...acc.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([d, [s, n]]) => ({ d, v: s / n }));
}

function abrirComparar() {
    const it = itemPorChave(det.key), todas = pracasDoItem(it);
    let ids = det.mercs.filter(id => todas.includes(id)).slice(0, COMP.MAX);
    if (ids.length < 2) ids = [...new Set([...ids, ...todas])].slice(0, COMP.MAX);
    det.comp = { ids, dias: (PERIODOS.find(p => p.dias === periodoDias) || PERIODOS[0]).dias, aviso: '', unica: todas.length < 2 };
    Graf.zoomH = null;
    history.pushState({ det: det.key, comp: true }, '');
    renderComparar();
    window.scrollTo(0, 0);
}
function fecharComparar() {
    det.comp = null;
    Graf.zoomH = null;
    Graf.fmtCurta = Graf.fmtLonga = null;
    renderDetalhe();
    window.scrollTo(0, 0);
}
function alternarPracaComp(id) {
    const c = det.comp, on = c.ids.includes(id);
    c.aviso = '';
    if (on) {
        if (c.ids.length === 1) return;
        c.ids = c.ids.filter(x => x !== id);
    } else if (c.ids.length >= COMP.MAX) {
        c.aviso = `Máximo de ${COMP.MAX} praças. Desmarque uma para incluir outra.`;
        return renderComparar();
    } else {
        c.ids = [...c.ids, id];
    }
    c.ids = dados.mercados.map(m => m.id).filter(x => c.ids.includes(x));
    Graf.zoomH = null;
    renderComparar();
}
// item numa praça só: troca o aviso pela comparação com os semelhantes das outras praças
function compararSemelhantes() {
    const c = det.comp, it = itemPorChave(det.key), origem = pracasDoItem(it)[0];
    const grupos = semelhantesDoItem(it, origem);
    const ids = dados.mercados.map(m => m.id).filter(id => id === origem || grupos[id]);
    c.sim = { origem, grupos, ids, cache: {} };
    c.ids = ids.slice(0, COMP.MAX);
    c.unica = false;
    c.aviso = '';
    Graf.zoomH = null;
    renderComparar();
    window.scrollTo(0, 0);
}
function renderUnica(it) {
    const origem = pracasDoItem(it)[0], grupos = semelhantesDoItem(it, origem), outras = Object.keys(grupos);
    const detalhe = it.d.replace(/\bLonga Vida\b/g, 'LV');
    const nome = `${it.p}${detalhe ? ' ' + detalhe : ''}`;
    el('vista-detalhe').innerHTML = `
        <div class="flex items-center justify-between">
            <button data-act="voltar" class="text-slate-200 hover:text-white font-semibold py-2 pr-3 -ml-1"><i class="fa-solid fa-arrow-left mr-1.5"></i>Voltar</button>
        </div>
        <div class="bg-mata-900 border border-mata-800 rounded-2xl p-5 space-y-4">
            <p class="text-xs font-bold text-verde-claro uppercase tracking-wide"><i class="fa-solid fa-scale-balanced mr-1"></i>Comparação entre praças</p>
            <p class="text-white text-lg leading-snug">O produto <b>${esc(nome)}</b>, com esse nome, só tem cotação em <b>${esc(nomeCurto(mercadoPor(origem)))}</b>.</p>
            ${outras.length ? `
                <p class="text-slate-300">Gostaria de comparar com produtos semelhantes em outras praças? Encontramos <b>${esc(it.p)}</b> em ${outras.length} outra${outras.length > 1 ? 's' : ''} praça${outras.length > 1 ? 's' : ''} (${outras.join(', ')}). Os diferentes tipos de cada praça entram juntos, pela média.</p>
                <div class="flex gap-2">
                    <button data-act="comp-sim" class="flex-1 bg-ouro hover:brightness-95 text-black font-bold rounded-2xl py-3 transition">Sim, comparar</button>
                    <button data-act="voltar" class="flex-1 bg-mata-800 hover:bg-mata-700 text-white font-semibold rounded-2xl py-3 transition-colors">Não</button>
                </div>`
            : `<p class="text-slate-300">Também não encontramos produtos semelhantes (${esc(it.p)}, ${UNIDADE[it.u]}) em outras praças.</p>`}
        </div>`;
}

function periodoComp(dias) {
    det.comp.dias = +dias;
    det.comp.aviso = '';
    Graf.zoomH = null;
    renderComparar();
}

function renderComparar() {
    const y = window.scrollY;
    const c = det.comp, it = itemPorChave(det.key);
    if (c.unica) { renderUnica(it); return window.scrollTo(0, y); }
    const todas = pracasComp(c, it);
    const fim = c.ids.map(id => { const p = serieComp(c, it, id); return p.length ? p[p.length - 1].d : ''; }).sort().pop();
    const ini = somarDias(fim, -c.dias);
    const semanal = c.dias > 91;   // 1 ano: média semanal; 1 e 3 meses: cada cotação
    const series = c.ids.map(id => {
        const bruto = serieComp(c, it, id).filter(p => p.d >= ini);
        return { id, cor: corMercado(id), bruto, pts: semanal ? agregarComp(bruto, false) : bruto };
    }).filter(s => s.pts.length);
    // rótulo do dia no gráfico: "Semana de dd/mm/aaaa" na média semanal; data normal nos demais
    Graf.fmtCurta = null;
    Graf.fmtLonga = semanal ? (d => `Semana de ${dataBR(d)}`) : null;

    const detalhe = it.d.replace(/\bLonga Vida\b/g, 'LV');
    const sub = [UNIDADE[it.u], it.e !== 'kg' ? it.e : ''].filter(Boolean).join(' · ');
    const box = 'bg-mata-900 border border-mata-800 rounded-2xl p-4';
    const est = series.map(s => {
        const v = s.bruto.map(p => p.v), u = s.bruto[s.bruto.length - 1];
        return { id: s.id, cor: s.cor, md: v.reduce((a, b) => a + b, 0) / v.length, mn: Math.min(...v), mx: Math.max(...v), n: v.length, u };
    });
    const maisBarata = est.length > 1 ? est.reduce((a, b) => (b.md < a.md ? b : a)) : null;
    const per = COMP.PERIODOS.find(p => p.dias === c.dias) || COMP.PERIODOS[COMP.PERIODOS.length - 1];

    el('vista-detalhe').innerHTML = `
        <div class="flex items-center justify-between">
            <button data-act="voltar" class="text-slate-200 hover:text-white font-semibold py-2 pr-3 -ml-1"><i class="fa-solid fa-arrow-left mr-1.5"></i>Voltar</button>
        </div>

        <div>
            <p class="text-xs font-bold text-verde-claro uppercase tracking-wide"><i class="fa-solid fa-scale-balanced mr-1"></i>Comparação entre praças</p>
            <h2 class="text-2xl font-bold text-white leading-tight mt-1">${esc(it.p)}${detalhe ? ` <span class="font-semibold text-slate-300">${esc(detalhe)}</span>` : ''}</h2>
            <p class="text-sm text-slate-400 mt-1">${esc(sub)} · preço comum</p>
        </div>
        ${c.sim ? `<div class="flex items-start gap-2 rounded-xl border border-ouro/40 bg-ouro/10 px-3 py-2.5 text-xs text-slate-200 leading-snug" role="note">
            <i class="fa-solid fa-circle-info text-ouro mt-0.5"></i>
            <div><p><b>Produtos semelhantes.</b> ${c.sim.origem}: o próprio item. Nas outras praças, média dos tipos encontrados:</p>
            <ul class="mt-1 space-y-0.5">${c.ids.filter(id => id !== c.sim.origem).map(id => `<li><b>${id}:</b> ${c.sim.grupos[id].map(x => esc([x.d || 'sem tipo', x.e !== 'kg' ? x.e : ''].filter(Boolean).join(' '))).join(' · ')}</li>`).join('')}</ul></div>
        </div>` : ''}

        <div>
            <div class="flex flex-wrap gap-1.5 bg-mata-900 border border-mata-800 rounded-2xl p-1.5" role="group" aria-label="Praças comparadas">
                ${todas.map(id => {
                    const on = c.ids.includes(id);
                    return `<button data-act="comp-merc" data-arg="${id}" aria-pressed="${on}" title="${esc(mercadoPor(id).nome)}" class="flex-1 basis-[22%] py-2.5 rounded-xl text-sm font-semibold transition-colors flex items-center justify-center gap-1.5 ${on ? 'bg-ouro text-mata-950' : 'text-slate-300 hover:bg-mata-800'}"><span class="w-2.5 h-2.5 rounded-full" style="background:${corMercado(id)}"></span>${id}</button>`;
                }).join('')}
            </div>
            <p class="text-xs ${c.aviso ? 'text-rose-400 font-semibold' : 'text-slate-500'} mt-1.5 px-1">${c.aviso || `Toque nas praças para comparar (até ${COMP.MAX}). Marcadas: ${c.ids.length}.`}</p>
        </div>

        <div class="flex flex-wrap gap-1.5" role="group" aria-label="Período da comparação">
            ${COMP.PERIODOS.map(p => `<button data-act="comp-per" data-arg="${p.dias}" aria-pressed="${p === per}" class="flex-none px-3 py-1.5 rounded-full text-xs font-semibold border whitespace-nowrap transition-colors ${p === per ? 'bg-ouro text-mata-950 border-ouro' : 'bg-mata-900 text-slate-300 border-mata-700 hover:border-verde/60'}">${p.rot}</button>`).join('')}
            <button data-act="mais" class="flex-none px-2.5 py-1.5 rounded-full text-xs font-semibold botao-ouro whitespace-nowrap transition-colors"><i class="fa-solid fa-lock mr-1 text-[10px]"></i>Mais dados sob consulta</button>
        </div>

        <div class="${box}">
            ${series.length ? Graf.historico('multi', series.map(({ id, cor, pts }) => ({ id, cor, pts }))) : '<p class="text-sm text-slate-400">Sem cotações neste período.</p>'}
            <p class="text-xs text-slate-500 mt-1">${semanal ? 'Média semanal do preço comum' : 'Preço comum'} de cada praça. Passe o cursor ou deslize o dedo no gráfico para ver os valores.</p>
        </div>

        <div class="${box}">
            <h3 class="font-bold text-white mb-2">Resumo do período (${per.rot.toLowerCase()})</h3>
            <table class="w-full text-sm">
                <tr class="text-xs text-slate-400"><th class="text-left font-semibold pb-1">Praça</th><th class="text-right font-semibold">Média</th><th class="text-right font-semibold">Menor</th><th class="text-right font-semibold">Maior</th><th class="text-right font-semibold">Última</th></tr>
                ${est.map(e => `<tr class="border-t border-mata-800">
                    <td class="py-2 font-bold text-white whitespace-nowrap"><span class="inline-block w-2.5 h-2.5 rounded-full mr-1.5" style="background:${e.cor}"></span>${e.id}</td>
                    <td class="text-right font-bold text-white">${preco(e.md)}${maisBarata && maisBarata.id === e.id ? ' <i class="fa-solid fa-arrow-down text-verde-claro text-[10px]" title="Menor média"></i>' : ''}</td>
                    <td class="text-right text-slate-200">${preco(e.mn)}</td>
                    <td class="text-right text-slate-200">${preco(e.mx)}</td>
                    <td class="text-right text-slate-200 whitespace-nowrap">${preco(e.u.v)}<span class="block text-[10px] text-slate-500">${dataCurta(e.u.d)}</span></td></tr>`).join('')}
            </table>
            ${maisBarata ? `<p class="text-xs text-slate-400 mt-2"><i class="fa-solid fa-arrow-down text-verde-claro mr-1"></i>Menor preço médio no período: <b class="text-white">${esc(nomeCurto(mercadoPor(maisBarata.id)))}</b>${est.filter(e => e.id !== maisBarata.id).map(e => ` · ${e.id} ${e.md > maisBarata.md ? '+' : ''}${((e.md / maisBarata.md - 1) * 100).toFixed(0)}%`).join('')}</p>` : ''}
        </div>`;
    window.scrollTo(0, y);
}
