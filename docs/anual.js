/* COTA CEA$A — Análise anualizada e previsão de preços
 * Sobrepõe até 6 anos (o atual + 5 anteriores) do preço comum de um produto numa praça,
 * em médias semanais (semana 1 = 1º a 7 de janeiro...). O ano atual fica com cor cheia;
 * cada ano anterior fica 10% mais apagado.
 * Previsão (próximas 12 semanas): parte do preço atual e aplica, semana a semana, a variação que
 * o produto teve no mesmo trecho de cada ano anterior. Linha = mediana; faixa = menor e maior caso.
 */
const ANUAL = {
    ANOS: 6,          // atual + 5 anteriores
    HORIZ: 12,        // semanas de previsão
    // escala do verde (ano atual, linha mais grossa) ao amarelo (ano mais antigo, mais fina)
    // escala do ano atual ao mais antigo: azul -> verde -> amarelo marca-texto (#FCFC30)
    ESCALA_HSL: [[212, 90, 56], [138, 77, 40], [60, 97, 59]],
    ocultos: new Set(),
};

const semanaDoAno = (iso) => {
    const d = new Date(iso + 'T12:00:00'), ini = new Date(d.getFullYear(), 0, 1, 12);
    return Math.min(51, Math.floor((d - ini) / 864e5 / 7));   // 0..51 (os 1-2 últimos dias entram na 52ª)
};
const inicioSemana = (ano, w) => new Date(ano, 0, 1 + 7 * w, 12);
const mediana = (v) => { const s = [...v].sort((a, b) => a - b), n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };

// {ano: [52 médias semanais ou null]}
function semanasPorAno(pts) {
    const acc = {};
    pts.forEach(({ d, v }) => {
        const a = +d.slice(0, 4), w = semanaDoAno(d);
        acc[a] = acc[a] || Array.from({ length: 52 }, () => []);
        acc[a][w].push(v);
    });
    const out = {};
    for (const a in acc) out[a] = semTrechosCurtos(acc[a].map(l => l.length ? l.reduce((x, y) => x + y, 0) / l.length : null));
    return out;
}
// semanas isoladas viram vazio: trecho = semanas com cotação, tolerando 1 semana vazia no meio;
// trecho com menos de 3 semanas com cotação é ponto perdido
const SEM_MIN = 3;
function semTrechosCurtos(s) {
    const out = [...s];
    let ini = null, ult = null, cont = 0;
    const fecha = () => { if (ini != null && cont < SEM_MIN) for (let k = ini; k <= ult; k++) out[k] = null; };
    s.forEach((v, w) => {
        if (v == null) return;
        if (ini != null && w - ult > 2) { fecha(); ini = null; }
        if (ini == null) { ini = w; cont = 0; }
        ult = w; cont++;
    });
    fecha();
    return out;
}
// valor da semana w do ano a (w pode passar de 51: vai para o ano seguinte); tolera 1 semana vazia
function valorSemana(sem, a, w) {
    while (w > 51) { a++; w -= 52; }
    const s = sem[a];
    if (!s) return null;
    for (const dw of [0, -1, 1]) { const v = s[w + dw]; if (v != null) return v; }
    return null;
}

// Elimina pontos soltos (ex.: cotação avulsa fora de safra): só valem trechos com pelo menos
// 4 cotações, em que entre uma cotação e a seguinte há no máximo 10 boletins (~2 semanas) sem
// cotação. Assim fica o fim de safra cotado de forma esparsa (ex.: Ponkan 2024) e saem as
// cotações isoladas a mais de 2 semanas de qualquer outra.
const SEQ_MIN = 4, FALHA_MAX = 10;
function serieFiltrada(it, mid) {
    const datas = mercadoPor(mid).datas, out = [];
    let run = [], vazios = 0;
    const fecha = () => { if (run.length >= SEQ_MIN) out.push(...run); run = []; };
    it.m[mid].h.forEach((v, i) => {
        if (v != null) { run.push({ d: datas[i], v }); vazios = 0; }
        else if (++vazios > FALHA_MAX) { fecha(); vazios = 0; }
    });
    fecha();
    return out;
}
const diasEntre = (a, b) => Math.round((new Date(b + 'T12:00:00') - new Date(a + 'T12:00:00')) / 864e5);

// Safra de cada ano anterior = maior trecho de semanas com cotação (tolera 1 semana vazia)
function safraDoAno(s) {
    let melhor = null, ini = null, fim = null, vazias = 0;
    s.forEach((v, w) => {
        if (v != null) { if (ini == null) ini = w; fim = w; vazias = 0; }
        else if (ini != null && ++vazias > 1) { if (!melhor || fim - ini > melhor[1] - melhor[0]) melhor = [ini, fim]; ini = null; vazias = 0; }
    });
    if (ini != null && (!melhor || fim - ini > melhor[1] - melhor[0])) melhor = [ini, fim];
    return melhor;
}

function calcularAnual(it, mid) {
    const pts = serieFiltrada(it, mid);
    if (!pts.length) return null;
    const sem = semanasPorAno(pts);
    const hoje = mercadoPor(mid).data, ult = pts[pts.length - 1];
    const atual = +hoje.slice(0, 4), wHoje = semanaDoAno(hoje);
    const anos = Object.keys(sem).map(Number).filter(a => a <= atual && a > atual - ANUAL.ANOS).sort((a, b) => b - a);
    const anteriores = anos.filter(a => a < +ult.d.slice(0, 4));
    // produto sazonal? (algum ano anterior com menos de ~10 meses de cotação)
    const safras = anteriores.map(a => safraDoAno(sem[a])).filter(Boolean);
    const sazonal = safras.some(([i, f]) => f - i < 44);
    const safraTipica = sazonal && safras.length >= 2
        ? [Math.round(mediana(safras.map(x => x[0]))), Math.round(mediana(safras.map(x => x[1])))] : null;
    const emSafra = diasEntre(ult.d, hoje) <= 14;   // cotado nas últimas 2 semanas

    const proj = [];
    let fimSafra = null, proxima = null;
    const w0 = emSafra ? semanaDoAno(ult.d) : wHoje, p0 = ult.v;
    const usados = new Set();
    if (emSafra) {
        // previsão: variação semana a semana dos anos anteriores, até onde eles ainda tinham safra
        const fimTipico = safraTipica && w0 <= safraTipica[1] ? safraTipica[1] : null;
        for (let h = 1; h <= ANUAL.HORIZ; h++) {
            if (fimTipico != null && w0 + h > fimTipico) { fimSafra = fimTipico; break; }   // para na safra típica
            const r = [];
            anteriores.forEach(a => {
                const b = valorSemana(sem, a, w0), f = valorSemana(sem, a, w0 + h);
                if (b && f) { r.push(f / b); usados.add(a); }
            });
            if (r.length < 2) { if (sazonal) fimSafra = w0 + h; break; }
            proj.push({ h, w: w0 + h, v: p0 * mediana(r), lo: p0 * Math.min(...r), hi: p0 * Math.max(...r), n: r.length });
        }
    } else {
        // fora de safra: quando a safra costumava recomeçar e com que preço
        const ini = [], preco0 = [];
        anos.filter(a => a < atual).forEach(a => {
            for (let k = 1; k <= 52; k++) {
                const v = valorSemana(sem, a, wHoje + k);
                if (v) { ini.push(k); preco0.push(v); usados.add(a); break; }
            }
        });
        if (ini.length >= 2) proxima = { w: wHoje + Math.round(mediana(ini)), v: mediana(preco0), lo: Math.min(...preco0), hi: Math.max(...preco0), n: ini.length };
    }
    const resumo = anos.map(a => {
        const v = sem[a].filter(x => x != null);
        return { a, md: v.reduce((x, y) => x + y, 0) / v.length, mn: Math.min(...v), mx: Math.max(...v), nesta: valorSemana(sem, a, wHoje), parcial: a === atual };
    });
    ANUAL.n = anos.length;
    return { sem, anos, atual, w0, wHoje, p0, ult, proj, emSafra, sazonal, safraTipica, fimSafra, proxima,
             usados: [...usados].sort((a, b) => b - a), resumo };
}

// transição pelo matiz (HSL): verde -> verde-limão -> amarelo, sem passar pelo oliva apagado
// k = 0 (ano atual) ... n-1 (ano mais antigo mostrado); a escala usa os anos que existem de fato
const posAno = (k) => ANUAL.n > 1 ? Math.min(1, k / (ANUAL.n - 1)) : 0;
function corAno(k) {
    const e = ANUAL.ESCALA_HSL, t = posAno(k) * (e.length - 1);
    const i = Math.min(e.length - 2, Math.floor(t)), f = t - i;   // trecho da escala e posição nele
    const [h1, s1, l1] = e[i], [h2, s2, l2] = e[i + 1];
    return `hsl(${(h1 + (h2 - h1) * f).toFixed(0)} ${(s1 + (s2 - s1) * f).toFixed(0)}% ${(l1 + (l2 - l1) * f).toFixed(0)}%)`;
}
function opAno() { return 1; }                                       // cor cheia em todos os anos
function espAno() { return 1.6; }                                   // mesma espessura fina em todos os anos (pouca sobreposição)

function renderAnual() {
    const y = window.scrollY;
    const it = itemPorChave(det.key), mid = det.anual.mid, merc = mercadoPor(mid);
    const A = calcularAnual(it, mid);
    if (!A) {
        el('vista-detalhe').innerHTML = `
            <button data-act="voltar" class="text-slate-200 hover:text-white font-semibold py-2 pr-3 -ml-1"><i class="fa-solid fa-arrow-left mr-1.5"></i>Voltar</button>
            <div class="bg-mata-900 border border-mata-800 rounded-2xl p-5 text-slate-300">Este produto não tem nenhum trecho com pelo menos ${SEQ_MIN} cotações próximas em ${esc(nomeCurto(merc))}, então não dá para analisar.</div>`;
        return;
    }
    const detalhe = it.d.replace(/\bLonga Vida\b/g, 'LV');
    const sub = [UNIDADE[it.u], it.e !== 'kg' ? it.e : ''].filter(Boolean).join(' · ');
    const box = 'bg-mata-900 border border-mata-800 rounded-2xl p-4';
    const pracas = dados.mercados.filter(x => it.m[x.id]);
    // linhas da tabela: 4, 8 e 12 semanas (ou a última semana antes do fim da safra)
    const hs = [4, 8, 12].filter(h => A.proj.some(p => p.h === h));
    const ultP = A.proj[A.proj.length - 1];
    if (ultP && !hs.includes(ultP.h)) hs.push(ultP.h);
    const dataSem = (w) => { const d = inicioSemana(+A.ult.d.slice(0, 4), w); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`; };
    const linhaProj = (rot, p) => p ? `<tr class="border-t border-mata-800"><td class="py-2.5 text-slate-300">${rot} <span class="text-slate-500 text-xs">(sem. de ${dataSem(p.w)})</span></td><td class="text-right font-bold text-white whitespace-nowrap">${R$(p.v)}</td><td class="text-right text-xs text-slate-400 whitespace-nowrap pl-2">${preco(p.lo)}–${preco(p.hi)}</td></tr>` : '';

    el('vista-detalhe').innerHTML = `
        <div class="flex items-center justify-between">
            <button data-act="voltar" class="text-slate-200 hover:text-white font-semibold py-2 pr-3 -ml-1"><i class="fa-solid fa-arrow-left mr-1.5"></i>Voltar</button>
        </div>

        <div>
            <p class="text-xs font-bold text-ouro uppercase tracking-wide"><i class="fa-solid fa-chart-line mr-1"></i>Análise anualizada e previsão</p>
            <h2 class="text-2xl font-bold text-white leading-tight mt-1">${esc(it.p)}${detalhe ? ` <span class="font-semibold text-slate-300">${esc(detalhe)}</span>` : ''}</h2>
            <p class="text-sm text-slate-400 mt-1">${esc(sub)} · ${esc(nomeCurto(merc))}</p>
        </div>

        ${pracas.length > 1 ? `<div class="flex flex-wrap gap-1.5 bg-mata-900 border border-mata-800 rounded-2xl p-1.5" role="group" aria-label="Praça da análise">
            ${pracas.map(x => `<button data-act="anual-merc" data-arg="${x.id}" aria-pressed="${x.id === mid}" class="flex-1 basis-[22%] py-2.5 rounded-xl text-sm font-semibold transition-colors ${x.id === mid ? 'bg-ouro text-mata-950' : 'text-slate-300 hover:bg-mata-800'}">${x.id}</button>`).join('')}
        </div>` : ''}

        <div class="${box} sempre-escuro">
            ${Graf.anual(A, ANUAL.ocultos)}
            <p class="text-xs text-slate-500 mt-2">Médias semanais do preço comum. Toque nos anos para mostrar ou esconder. Pontilhado: previsão; faixa: menor e maior caso dos anos anteriores. ${A.proj.some(p => p.w > 51) ? 'Meses em amarelo: começo do ano seguinte.' : ''}</p>
        </div>

        <div class="${box}">
            <h3 class="font-bold text-white mb-1">Previsão de preço</h3>
            ${A.safraTipica ? `<p class="text-sm text-slate-300 mb-2"><i class="fa-solid fa-seedling text-verde-claro mr-1.5"></i>Safra típica: <b class="text-white">${dataSem(A.safraTipica[0])} a ${dataSem(A.safraTipica[1])}</b></p>` : ''}
            ${A.emSafra && A.proj.length ? `
            <p class="text-xs text-slate-400 mb-2">${A.sazonal ? 'Em safra. ' : ''}A partir de ${R$(A.p0)} (${dataCurta(A.ult.d)}), repetindo o comportamento de ${A.usados.join(', ')} nas mesmas semanas.</p>
            <table class="w-full text-[15px]">
                <tr><th></th><th class="text-right text-xs text-slate-400 font-semibold pb-1">Previsto</th><th class="text-right text-xs text-slate-400 font-semibold pb-1 pl-2">Faixa</th></tr>
                ${hs.map(h => linhaProj(`Em ${h} semana${h > 1 ? 's' : ''}`, A.proj.find(p => p.h === h))).join('')}
            </table>
            ${A.fimSafra ? `<p class="text-sm text-slate-300 mt-2"><i class="fa-solid fa-flag-checkered text-ouro mr-1.5"></i>Fim de safra provável: <b class="text-white">semana de ${dataSem(A.fimSafra)}</b> (nos anos anteriores a cotação parava por aí).</p>` : ''}`
            : A.emSafra ? `<p class="text-sm text-slate-400">${A.fimSafra ? `Fim de safra: nos anos anteriores a cotação parava por volta da semana de ${dataSem(A.fimSafra)}, então não há base para prever além disso.` : `Histórico insuficiente para prever: são necessários pelo menos 2 anos anteriores com cotação nas mesmas semanas${A.anos.length < 2 ? ` (esta praça tem dados desde ${A.anos[A.anos.length - 1] || A.atual})` : ''}.`}</p>`
            : `<p class="text-sm text-slate-300"><i class="fa-solid fa-moon text-slate-400 mr-1.5"></i>Fora de safra (última cotação em ${dataBR(A.ult.d)}).</p>
               ${A.proxima ? `<p class="text-sm text-slate-300 mt-2">Nos anos anteriores (${A.usados.join(', ')}), a cotação recomeçou por volta da <b class="text-white">semana de ${dataSem(A.proxima.w)}</b>, com preço inicial em torno de <b class="text-white">${R$(A.proxima.v)}</b> <span class="text-slate-500">(${preco(A.proxima.lo)}–${preco(A.proxima.hi)})</span>.</p>`
                 : '<p class="text-sm text-slate-400 mt-2">Sem anos anteriores suficientes para estimar o início da próxima safra.</p>'}`}
            <p class="text-[11px] text-slate-500 mt-2">Estimativa a partir dos anos anteriores, sem pontos soltos (trechos com ${SEQ_MIN}+ cotações). Não considera clima ou mercado deste ano; use como referência, não como garantia.</p>
        </div>

        <div class="${box} overflow-x-auto">
            <h3 class="font-bold text-white mb-2">Comparação entre os anos</h3>
            <table class="w-full text-sm">
                <tr class="text-xs text-slate-400"><th class="text-left font-semibold pb-1">Ano</th><th class="text-right font-semibold">Nesta semana</th><th class="text-right font-semibold">Média</th><th class="text-right font-semibold">Mín.</th><th class="text-right font-semibold">Máx.</th></tr>
                ${A.resumo.map((r, k) => `<tr class="border-t border-mata-800" style="opacity:${opAno(k)}">
                    <td class="py-2 font-bold text-white whitespace-nowrap"><span class="inline-block w-2.5 h-2.5 rounded-full mr-1.5" style="background:${corAno(k)}"></span>${r.a}${r.parcial ? '<span class="text-[10px] text-slate-500 font-semibold ml-1">até agora</span>' : ''}</td>
                    <td class="text-right font-bold text-white">${r.nesta != null ? preco(r.nesta) : '–'}</td>
                    <td class="text-right text-slate-200">${preco(r.md)}</td>
                    <td class="text-right text-slate-200">${preco(r.mn)}</td>
                    <td class="text-right text-slate-200">${preco(r.mx)}</td></tr>`).join('')}
            </table>
        </div>`;
    window.scrollTo(0, y);
}

function abrirAnual() {
    ANUAL.zoom = null;
    det.anual = { mid: det.mercs[0] };
    history.pushState({ det: det.key, anual: true }, '');
    renderAnual();
    window.scrollTo(0, 0);
}
function fecharAnual() {
    det.anual = null;
    renderDetalhe();
    window.scrollTo(0, 0);
}
function alternarAnoAnual(a) {
    a = +a;
    if (ANUAL.ocultos.has(a)) ANUAL.ocultos.delete(a); else ANUAL.ocultos.add(a);
    renderAnual();
}
