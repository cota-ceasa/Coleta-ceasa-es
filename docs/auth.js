// Login local: cadastro, entrada e recuperação de acesso.
// Os acessos ficam salvos só neste aparelho (localStorage). Em produção, isso viria de um servidor.

// SHA-256 em JavaScript puro. O navegador só oferece crypto.subtle em páginas seguras
// (https ou localhost); em http pela rede local (ex.: celular) usamos esta versão.
function sha256js(texto) {
    const rr = (v, a) => (v >>> a) | (v << (32 - a));
    const by = Array.from(new TextEncoder().encode(texto));
    const bits = by.length * 8;
    by.push(0x80);
    while (by.length % 64 !== 56) by.push(0);
    for (const w of [Math.floor(bits / 4294967296), bits >>> 0]) for (let s = 24; s >= 0; s -= 8) by.push((w >>> s) & 255);
    const K = [], H = [];
    for (let c = 2; K.length < 64; c++) {
        let primo = true;
        for (let d = 2; d * d <= c; d++) if (c % d === 0) { primo = false; break; }
        if (!primo) continue;
        if (H.length < 8) H.push((Math.sqrt(c) % 1) * 4294967296 | 0);
        K.push((Math.cbrt(c) % 1) * 4294967296 | 0);
    }
    for (let i = 0; i < by.length; i += 64) {
        const w = new Array(64);
        for (let t = 0; t < 16; t++) w[t] = (by[i + 4 * t] << 24) | (by[i + 4 * t + 1] << 16) | (by[i + 4 * t + 2] << 8) | by[i + 4 * t + 3];
        for (let t = 16; t < 64; t++) {
            const s0 = rr(w[t - 15], 7) ^ rr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
            const s1 = rr(w[t - 2], 17) ^ rr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
            w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
        }
        let [a, b, c, d, e, f, g, h] = H;
        for (let t = 0; t < 64; t++) {
            const S1 = rr(e, 6) ^ rr(e, 11) ^ rr(e, 25), ch = (e & f) ^ (~e & g);
            const t1 = (h + S1 + ch + K[t] + w[t]) | 0;
            const S0 = rr(a, 2) ^ rr(a, 13) ^ rr(a, 22), mj = (a & b) ^ (a & c) ^ (b & c);
            const t2 = (S0 + mj) | 0;
            h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
        }
        [a, b, c, d, e, f, g, h].forEach((v, k) => { H[k] = (H[k] + v) | 0; });
    }
    return H.map(v => (v >>> 0).toString(16).padStart(8, '0')).join('');
}

async function hashSenha(sal, senha) {
    const txt = sal + senha;
    if (window.crypto && crypto.subtle) {
        const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(txt));
        return Array.from(new Uint8Array(buf)).map(x => x.toString(16).padStart(2, '0')).join('');
    }
    return sha256js(txt);
}

const Auth = (() => {
    const K_USERS = 'cc-users', K_SESS = 'cc-sess';
    let usuario = null;                       // { id, nome } quando logado
    let modo = 'in', erro = '', f = { nome: '', tel: '', id: '' }, recId = null;

    const usuarios = () => lerLS(K_USERS, {});
    const sal = () => Array.from(crypto.getRandomValues(new Uint8Array(8))).map(x => x.toString(16).padStart(2, '0')).join('');

    const INPUT = 'w-full bg-mata-950 border border-mata-700 rounded-xl px-4 py-3 text-base text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-ouro mb-4';
    const LABEL = 'block text-sm text-slate-300 mb-1.5';
    const BTN = 'w-full bg-ouro hover:bg-ouro-escuro text-mata-950 font-bold rounded-xl py-3.5 text-base mt-1';
    const LNK = 'w-full text-slate-300 underline py-3 text-sm';

    function topo(titulo, sub) {
        return `<div class="flex items-center justify-between px-4 h-14 border-b border-mata-800 bg-mata-900 sticky top-0">
                    <span class="font-black text-verde-claro">COTA CEA<span class="text-ouro">$</span>A</span>
                    <button onclick="fecharFolha()" aria-label="Fechar" class="text-slate-400 hover:text-white p-2"><i class="fa-solid fa-xmark text-lg"></i></button>
                </div>
                <div class="px-5 py-6"><h2 class="text-2xl font-bold text-white leading-tight">${titulo}</h2><p class="text-slate-400 mt-1 mb-5">${sub}</p>`;
    }
    const erroH = () => erro ? `<div role="alert" class="bg-rose-500/15 text-rose-300 rounded-xl px-3 py-2.5 text-sm mb-4">${esc(erro)}</div>` : '';

    function html() {
        if (modo === 'rec') {
            return topo('Recuperar acesso', 'Digite o nome e o telefone que você cadastrou.') + erroH() +
                `<label class="${LABEL}" for="rn">Seu nome</label><input id="rn" class="${INPUT}" autocomplete="off" value="${esc(f.nome)}">
                 <label class="${LABEL}" for="rw">Telefone com DDD</label><input id="rw" type="tel" inputmode="tel" class="${INPUT}" autocomplete="off" onkeydown="if(event.key==='Enter')Auth.achar()">
                 <button class="${BTN}" onclick="Auth.achar()">Recuperar</button>
                 <button class="${LNK}" onclick="Auth.modo('in')">← Voltar</button></div>`;
        }
        if (modo === 'rec2') {
            return topo('Acesso encontrado', 'Seu usuário é:') +
                `<div class="bg-mata-900 border border-mata-800 rounded-xl px-4 py-3 mb-4"><b class="text-2xl text-ouro">${esc(recId)}</b></div>
                 <p class="text-slate-400 text-sm mb-4">A senha antiga não pode ser mostrada. Crie uma nova.</p>${erroH()}
                 <label class="${LABEL}" for="np">Nova senha</label><input id="np" type="password" class="${INPUT}" autocomplete="new-password" onkeydown="if(event.key==='Enter')Auth.novaSenha()">
                 <button class="${BTN}" onclick="Auth.novaSenha()">Salvar e entrar</button></div>`;
        }
        const novo = modo === 'new';
        return topo(novo ? 'Criar acesso' : 'Entrar', novo ? 'Salve seus favoritos e preferências.' : 'Entre para ver seus produtos favoritos.') + erroH() +
            (novo ? `<label class="${LABEL}" for="nm">Seu nome</label><input id="nm" class="${INPUT}" autocomplete="name" value="${esc(f.nome)}">
                     <label class="${LABEL}" for="ph">Telefone com DDD</label><input id="ph" type="tel" inputmode="tel" class="${INPUT}" autocomplete="tel" placeholder="(27) 99999-9999" value="${esc(f.tel)}">` : '') +
            `<label class="${LABEL}" for="em">Usuário (e-mail ou apelido)</label><input id="em" class="${INPUT}" autocapitalize="none" autocomplete="username" value="${esc(f.id)}">
             <label class="${LABEL}" for="pw">Senha</label><input id="pw" type="password" class="${INPUT}" autocomplete="${novo ? 'new-password' : 'current-password'}" onkeydown="if(event.key==='Enter')Auth.enviar()">
             <button class="${BTN}" onclick="Auth.enviar()">${novo ? 'Criar acesso' : 'Entrar'}</button>
             <button class="${LNK}" onclick="Auth.modo('${novo ? 'in' : 'new'}')">${novo ? 'Já tenho acesso' : 'Criar um acesso novo'}</button>` +
            (novo ? '' : `<button class="${LNK}" style="margin-top:-6px" onclick="Auth.modo('rec')">Esqueci meu usuário ou senha</button>`) +
            `<p class="text-xs text-slate-500 mt-4">Os acessos ficam salvos só neste aparelho. No app real, o cadastro fica no servidor.</p></div>`;
    }

    function mostrar() { abrirFolha(html()); }
    function falha(m) { erro = m; mostrar(); }

    function entrar(id) {
        const u = usuarios()[id];
        usuario = { id, nome: u.nome };
        gravarLS(K_SESS, id);
        fecharFolha();
        aoMudarUsuario();
    }

    return {
        usuario: () => usuario,
        abrir(m) { modo = m || 'in'; erro = ''; mostrar(); },
        modo(m) { modo = m; erro = ''; mostrar(); },

        async enviar() {
            const novo = modo === 'new';
            const id = el('em').value.trim().toLowerCase(), pw = el('pw').value;
            f.id = id;
            if (novo) { f.nome = el('nm').value.trim(); f.tel = el('ph').value; }
            if (!id) return falha('Digite seu usuário.');
            if (!pw) return falha('Digite sua senha.');
            const u = usuarios();
            if (novo) {
                const tel = f.tel.replace(/\D/g, '');
                if (!f.nome) return falha('Digite seu nome.');
                if (tel.length < 10 || tel.length > 11) return falha('Digite o telefone com DDD, por exemplo (27) 99999-9999.');
                if (pw.length < 4) return falha('Use uma senha com pelo menos 4 caracteres.');
                if (u[id]) return falha('Esse usuário já existe. Use "Já tenho acesso".');
                const s = sal();
                u[id] = { nome: f.nome, salt: s, hash: await hashSenha(s, pw), tel, prefs: aoCriarUsuario() };
                gravarLS(K_USERS, u);
                f = { nome: '', tel: '', id: '' };
                entrar(id);
            } else {
                if (!u[id]) return falha('Usuário ou senha incorretos.');
                if (await hashSenha(u[id].salt, pw) !== u[id].hash) return falha('Usuário ou senha incorretos.');
                f = { nome: '', tel: '', id: '' };
                entrar(id);
            }
        },

        achar() {
            const nm = el('rn').value.trim().toLowerCase(), tl = el('rw').value.replace(/\D/g, '');
            f.nome = el('rn').value.trim();
            if (!nm || !tl) return falha('Preencha o nome e o telefone.');
            const u = usuarios();
            const achados = Object.keys(u).filter(k => u[k].tel === tl && u[k].nome.trim().toLowerCase() === nm);
            if (!achados.length) return falha('Não encontramos um acesso com esses dados.');
            recId = achados[0]; modo = 'rec2'; erro = ''; mostrar();
        },

        async novaSenha() {
            const pw = el('np').value;
            if (pw.length < 4) return falha('Use uma senha com pelo menos 4 caracteres.');
            const u = usuarios();
            u[recId].hash = await hashSenha(u[recId].salt, pw);
            gravarLS(K_USERS, u);
            entrar(recId);
        },

        sair() {
            usuario = null;
            gravarLS(K_SESS, null);
            fecharFolha();
            aoMudarUsuario();
        },

        // restaura a sessão salva neste aparelho
        restaurar() {
            const id = lerLS(K_SESS, null);
            if (id && usuarios()[id]) usuario = { id, nome: usuarios()[id].nome };
        },

        lerPrefs() { return usuario ? (usuarios()[usuario.id].prefs || {}) : null; },
        gravarPrefs(p) {
            if (!usuario) return;
            const u = usuarios();
            if (!u[usuario.id]) return;
            u[usuario.id].prefs = { ...(u[usuario.id].prefs || {}), ...p };
            gravarLS(K_USERS, u);
        }
    };
})();
