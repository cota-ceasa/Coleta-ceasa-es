// Funções utilitárias compartilhadas (carregado primeiro)

const el = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const norm = (s) => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const preco = (v) => v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const R$ = (v) => 'R$ ' + preco(v);

// localStorage com tolerância a falhas (modo privado, bloqueio de dados do site etc.)
const MEM = {};
function lerLS(chave, padrao) {
    try { const v = localStorage.getItem(chave); return v ? JSON.parse(v) : (MEM[chave] ?? padrao); }
    catch { return MEM[chave] ?? padrao; }
}
function gravarLS(chave, valor) {
    MEM[chave] = valor;
    try { localStorage.setItem(chave, JSON.stringify(valor)); } catch { /* ignora */ }
}

// Datas em texto ISO (AAAA-MM-DD), sem deslocamento de fuso
function dataBR(iso, comDiaSemana) {
    const [a, m, d] = iso.split('-').map(Number);
    const txt = `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${a}`;
    if (!comDiaSemana) return txt;
    const dia = new Date(a, m - 1, d).toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '');
    return `${dia}, ${txt}`;
}
const dataCurta = (iso) => iso.slice(8) + '/' + iso.slice(5, 7);
function somarDias(iso, n) {
    const [a, m, d] = iso.split('-').map(Number);
    const dt = new Date(a, m - 1, d + n);
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
}

// Selo de variação percentual: ▲ sobe (verde), ▼ cai (vermelho), ■ estável
function chipVar(c) {
    if (c == null || !isFinite(c)) return '';
    const k = c > 0.05 ? 'up' : c < -0.05 ? 'dn' : 'fl';
    const cls = { up: 'text-verde-claro bg-verde/15', dn: 'text-rose-400 bg-rose-500/15', fl: 'text-slate-400 bg-mata-800' }[k];
    const s = k === 'up' ? '▲ +' : k === 'dn' ? '▼ −' : '■ ';
    return `<span class="inline-block text-[13px] font-bold px-2 py-0.5 rounded-lg whitespace-nowrap ${cls}">${s}${Math.abs(c).toFixed(1).replace('.', ',')}%</span>`;
}

// Distância de edição (com troca de letras vizinhas) para tolerar erros de digitação na busca
function distancia(a, b) {
    const m = a.length, n = b.length, d = [];
    for (let i = 0; i <= m; i++) d[i] = [i];
    for (let j = 1; j <= n; j++) d[0][j] = j;
    for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++) {
        const c = a[i - 1] === b[j - 1] ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
    return d[m][n];
}

// Folha (tela sobreposta) usada por login e configurações
function abrirFolha(html) {
    const f = el('folha');
    el('folha-conteudo').innerHTML = html;
    f.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    const campo = f.querySelector('input');
    // foca o primeiro campo, mas só se a pessoa ainda não tiver tocado em outro
    if (campo) setTimeout(() => { if (!f.contains(document.activeElement)) campo.focus(); }, 50);
}
function fecharFolha() {
    el('folha').classList.add('hidden');
    document.body.style.overflow = '';
}
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fecharFolha(); });
