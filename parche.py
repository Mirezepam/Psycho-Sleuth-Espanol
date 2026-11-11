"""Instalador del parche en español para Psycho-Sleuth (Steam).

Modifica los archivos de tu propia copia del juego y guarda una copia de seguridad
de los originales en la carpeta del juego (_respaldo_parche_es).
"""
import sys, os, re, json, gzip, shutil, struct, hashlib, zlib, glob, subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DATOS = os.path.join(BASE, "datos", "traduccion.json.gz")
H = lambda s: hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]
RESPALDO = "_respaldo_parche_es"

D = "Psycho Sleuth_Data"
ARCHIVOS = {
    "dialogos": os.path.join(D, "StreamingAssets", "DDetective", "Windows", "ddetective.scenarios.asset"),
    "interfaz": os.path.join(D, "resources.assets"),
    "guion2": os.path.join(D, "sharedassets0.assets"),
    "catalogo": os.path.join(D, "StreamingAssets", "aa", "catalog.bin"),
}
CARPETA_AA = os.path.join(D, "StreamingAssets", "aa", "StandaloneWindows64")
PATRON_SUBS = "defaultlocalgroup_assets_all_*.bundle"


def pausa():
    if getattr(sys, "frozen", False):
        input("\nPulsa Enter para salir...")


# ---------------------------------------------------------------- buscar el juego
def bibliotecas_steam():
    rutas = []
    try:
        import winreg
        for raiz, clave in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(raiz, clave) as k:
                    for nombre in ("SteamPath", "InstallPath"):
                        try: rutas.append(winreg.QueryValueEx(k, nombre)[0])
                        except OSError: pass
            except OSError: pass
    except ImportError:
        pass
    rutas += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    libs = []
    for r in rutas:
        vdf = os.path.join(r, "steamapps", "libraryfolders.vdf")
        libs.append(r)
        if os.path.isfile(vdf):
            for m in re.finditer(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8", errors="ignore").read()):
                libs.append(m.group(1).replace("\\\\", "\\"))
    for letra in "CDEFGHIJ":
        libs += [f"{letra}:\\SteamLibrary", f"{letra}:\\Steam"]
    return list(dict.fromkeys(libs))


def es_juego(p):
    return p and os.path.isfile(os.path.join(p, ARCHIVOS["dialogos"]))


def buscar_juego():
    if len(sys.argv) > 1 and es_juego(sys.argv[1]):
        return sys.argv[1]
    if es_juego(os.getcwd()):
        return os.getcwd()
    for lib in bibliotecas_steam():
        p = os.path.join(lib, "steamapps", "common", "Psycho-Sleuth")
        if es_juego(p):
            return p
    print("No encontré el juego automáticamente.")
    print('En Steam: clic derecho en Psycho-Sleuth > Administrar > Ver archivos locales, copia esa ruta y pégala aquí.')
    while True:
        p = input("Carpeta del juego: ").strip().strip('"')
        if es_juego(p):
            return p
        print("Esa carpeta no contiene el juego (falta 'Psycho Sleuth_Data'). Prueba otra vez.")


def juego_abierto():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Psycho Sleuth.exe"], capture_output=True, text=True).stdout
        return "Psycho Sleuth.exe" in out
    except Exception:
        return False


# ---------------------------------------------------------------- utilidades Unity
def leer_cadena(raw, p, maximo=20000):
    if p + 4 > len(raw): return None
    L = struct.unpack_from("<i", raw, p)[0]
    if L < 0 or L > maximo or p + 4 + L > len(raw): return None
    try: s = raw[p + 4:p + 4 + L].decode("utf-8")
    except UnicodeDecodeError: return None
    return s, (p + 4 + L + 3) & ~3


def cadena_bytes(s):
    b = s.encode("utf-8")
    return struct.pack("<i", len(b)) + b + b"\0" * ((-len(b)) % 4)


def nombre_mb(raw):
    r = leer_cadena(raw, 28, 200)
    return r[0] if r else ""


def crc_bundle(p):
    """CRC que Addressables comprueba: crc32 de los bloques descomprimidos del UnityFS."""
    from UnityPy.helpers.CompressionHelper import decompress_lz4, decompress_lzma
    def dec(flag, d, n):
        t = flag & 0x3f
        return d if t == 0 else decompress_lzma(d) if t == 1 else decompress_lz4(d, n)
    b = open(p, "rb").read(); i = 0
    def cstr():
        nonlocal i
        j = b.index(b"\0", i); i = j + 1
    cstr(); ver = struct.unpack_from(">I", b, i)[0]; i += 4; cstr(); cstr()
    _, csz, usz, flags = struct.unpack_from(">qIII", b, i); i += 20
    if ver >= 7: i = (i + 15) & ~15
    if flags & 0x80: info = b[len(b) - csz:]
    else: info = b[i:i + csz]; i += csz
    info = dec(flags, info, usz)
    if flags & 0x200: i = (i + 15) & ~15
    n = struct.unpack_from(">i", info, 16)[0]; q = 20; c = 0
    for _ in range(n):
        u, cs, f = struct.unpack_from(">IIH", info, q); q += 10
        c = zlib.crc32(dec(f, b[i:i + cs], u), c); i += cs
    return c


# ---------------------------------------------------------------- parches
def parche_dialogos(src, dst, tr):
    import UnityPy
    env = UnityPy.load(src); n = 0
    for o in env.objects:
        if o.type.name != "MonoBehaviour": continue
        t = o.read_typetree(); tocado = False
        for key in ("importGridList", "settingList"):
            for g in t.get(key, []) if isinstance(t, dict) else []:
                rows = g["rows"]
                if not rows: continue
                hdr = rows[g["headerRow"]]["strings"]
                if "English" not in hdr: continue
                ci = hdr.index("English")
                for r in rows[g["headerRow"] + 1:]:
                    s = r["strings"]
                    if ci < len(s) and s[ci].strip():
                        es = tr.get(H(s[ci]))
                        if es: s[ci] = es; n += 1; tocado = True
        if tocado: o.save_typetree(t)
    open(dst, "wb").write(env.file.save(packer="lz4"))
    return n


def parche_interfaz(src, dst, tr):
    import UnityPy
    env = UnityPy.load(src)
    obj = [o for o in env.objects if o.type.name == "MonoBehaviour" and o.path_id == 18032]
    if not obj:
        obj = [o for o in env.objects if o.type.name == "MonoBehaviour" and nombre_mb(o.get_raw_data()) == "I2Languages"]
    if not obj: raise RuntimeError("no encontré la tabla de idiomas (I2Languages)")
    o = obj[0]; raw = o.get_raw_data()
    buf = bytearray(); pos = 0; p = 0; n = 0
    while p + 4 <= len(raw):
        if struct.unpack_from("<i", raw, p)[0] == 5:
            q, vals, ok = p + 4, [], True
            for _ in range(5):
                r = leer_cadena(raw, q)
                if r is None: ok = False; break
                vals.append((q, r[0], r[1])); q = r[1]
            if ok and any(v[1] for v in vals):
                off, en, fin = vals[2]
                es = tr.get(H(en)) if en.strip() else None
                if es:
                    buf += raw[pos:off] + cadena_bytes(es); pos = fin; n += 1
                p = q; continue
        p += 4
    buf += raw[pos:]
    o.set_raw_data(bytes(buf))
    open(dst, "wb").write(env.file.save())
    return n


def parche_guion2(src, dst, tr):
    import UnityPy
    texto = re.compile(r"[ .,!?…\"'—]")
    env = UnityPy.load(src)
    obj = [o for o in env.objects if o.type.name == "MonoBehaviour" and o.path_id == 7425]
    if not obj: return 0
    o = obj[0]; raw = o.get_raw_data()
    buf = bytearray(); pos = 0; i = 0; n = 0
    while i + 4 <= len(raw):
        r = leer_cadena(raw, i, 4000)
        if r and r[0]:
            s, fin = r
            es = tr.get(H(s)) if texto.search(s) else None
            if es:
                buf += raw[pos:i] + cadena_bytes(es); pos = fin; n += 1
            i = fin; continue
        i += 4
    buf += raw[pos:]
    o.set_raw_data(bytes(buf))
    open(dst, "wb").write(env.file.save())
    return n


def parche_subs(src, dst, tr):
    import UnityPy
    tiempo = re.compile(r"^\s*\d+\s*$|-->")
    env = UnityPy.load(src); n = 0
    for o in env.objects:
        if o.type.name != "TextAsset": continue
        d = o.read()
        if not d.m_Name.endswith("_en"): continue
        txt = d.m_Script if isinstance(d.m_Script, str) else d.m_Script.decode("utf-8")
        nuevo = []
        for l in txt.splitlines(keepends=True):
            s = l.strip()
            es = tr.get(H(s)) if s and not tiempo.search(l) else None
            if es:
                fin = l[len(l.rstrip("\r\n")):]
                nuevo.append(l[:len(l) - len(l.lstrip())] + es + fin); n += 1
            else:
                nuevo.append(l)
        d.m_Script = "".join(nuevo); d.save()
    open(dst, "wb").write(env.file.save(packer="lz4"))
    return n


def parche_catalogo(src, dst, crc_viejo, crc_nuevo):
    b = open(src, "rb").read()
    v, nv = struct.pack("<I", crc_viejo), struct.pack("<I", crc_nuevo)
    k = b.count(v)
    if k == 0: raise RuntimeError("no encontré el CRC de los subtítulos en catalog.bin")
    open(dst, "wb").write(b.replace(v, nv))


# ---------------------------------------------------------------- instalar / desinstalar
def rutas(juego):
    subs = glob.glob(os.path.join(juego, CARPETA_AA, PATRON_SUBS))
    r = {k: os.path.join(juego, v) for k, v in ARCHIVOS.items()}
    if subs: r["subtitulos"] = subs[0]
    return r


def respaldar(juego, r):
    bk = os.path.join(juego, RESPALDO); os.makedirs(bk, exist_ok=True)
    out = {}
    for k, p in r.items():
        b = os.path.join(bk, os.path.basename(p))
        if not os.path.exists(b):
            shutil.copy2(p, b)
        out[k] = b
    return out


def instalar(juego):
    tr = json.load(gzip.open(DATOS, "rt", encoding="utf-8"))
    r = rutas(juego)
    print("Guardando copia de seguridad de los archivos originales...")
    orig = respaldar(juego, r)
    tmp = os.path.join(juego, RESPALDO, "_tmp"); os.makedirs(tmp, exist_ok=True)
    t = lambda k: os.path.join(tmp, os.path.basename(r[k]))

    print("[1/5] Diálogos...", end=" ", flush=True)
    print(parche_dialogos(orig["dialogos"], t("dialogos"), tr["dialogos"]), "líneas")
    print("[2/5] Menús e interfaz...", end=" ", flush=True)
    print(parche_interfaz(orig["interfaz"], t("interfaz"), tr["interfaz"]), "textos")
    print("[3/5] Segunda copia del guion...", end=" ", flush=True)
    todo = dict(tr["dialogos"]); todo.update(tr["interfaz"])
    print(parche_guion2(orig["guion2"], t("guion2"), todo), "textos")
    if "subtitulos" in r:
        print("[4/5] Subtítulos de vídeo...", end=" ", flush=True)
        print(parche_subs(orig["subtitulos"], t("subtitulos"), tr["subtitulos"]), "líneas")
        print("[5/5] Catálogo (comprobación CRC)...", end=" ", flush=True)
        parche_catalogo(orig["catalogo"], t("catalogo"), crc_bundle(orig["subtitulos"]), crc_bundle(t("subtitulos")))
        print("ok")
    else:
        print("[4/5] No encontré el paquete de subtítulos; se omite.")

    for k in r:
        if os.path.exists(t(k)):
            shutil.copyfile(t(k), r[k])
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n¡Parche instalado!")
    print("IMPORTANTE: en el juego elige el idioma ENGLISH (Opciones > Idioma). Se mostrará en español.")


def desinstalar(juego):
    bk = os.path.join(juego, RESPALDO)
    if not os.path.isdir(bk):
        print("No hay copia de seguridad. Usa Steam > Propiedades > Archivos instalados > Verificar integridad.")
        return
    for k, p in rutas(juego).items():
        b = os.path.join(bk, os.path.basename(p))
        if os.path.exists(b): shutil.copyfile(b, p)
    shutil.rmtree(bk, ignore_errors=True)
    print("Parche desinstalado: el juego vuelve a estar como el original.")


def main():
    print("=" * 56)
    print("   Psycho-Sleuth  -  Parche de traducción al español")
    print("=" * 56)
    juego = buscar_juego()
    print("Juego encontrado en:", juego, "\n")
    while juego_abierto():
        input("Cierra el juego y pulsa Enter para continuar...")
    instalado = os.path.isdir(os.path.join(juego, RESPALDO))
    print("1) Instalar" + (" / reinstalar" if instalado else "") + " el parche")
    print("2) Desinstalar el parche")
    op = input("Elige 1 o 2: ").strip()
    print()
    if op == "1": instalar(juego)
    elif op == "2": desinstalar(juego)
    else: print("Opción no válida.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nERROR:", e)
        print("Si el juego se actualizó, puede que el parche necesite una nueva versión.")
    pausa()
