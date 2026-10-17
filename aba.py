#!/usr/bin/env python3
"""
Générateur ABA (Assumption-Based Argumentation) avec préférences (ABA+).

Fonctionnalités :
  1. Parsing : littéraux, hypothèses, contraires, règles, préférences.
  2. Conversion en cadre ABA non circulaire ET atomique (dépliage des règles :
     tous les corps de règles ne contiennent plus que des hypothèses).
  3. Construction de tous les arguments et de toutes les attaques.
  4. Préférences entre hypothèses -> attaques normales / inverses (reverse).

Usage :
    python aba.py exemple.txt
    cat exemple.txt | python aba.py
"""
import re
import sys
from dataclasses import dataclass
from itertools import product


class ABAError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Structures de données
# --------------------------------------------------------------------------- #
@dataclass
class Rule:
    id: str
    head: str
    body: tuple
    origins: tuple = ()  # arbres de dérivation d'origine (après dépliage)

    def __str__(self):
        return f"[{self.id}]: {self.head} <- {','.join(self.body)}"


@dataclass
class Argument:
    name: str
    claim: str
    support: set
    rule: str  # id de la règle (None pour un argument {a} |- a)

    def __str__(self):
        sup = ",".join(sorted(self.support))
        return f"{self.name}: [{sup}] |- {self.claim}"



# Cadre ABA

class ABA:
    def __init__(self, literals, assumptions, contraries, rules, strict_pref=None):
        self.literals = list(dict.fromkeys(literals))
        self.assumptions = list(dict.fromkeys(assumptions))
        self.contrary = dict(contraries)
        self.rules = list(rules)
        # strict_pref : ensemble de couples (x, y) signifiant "x > y"
        self.strict_pref = set(strict_pref or ())
        self._validate()

   
    def _validate(self):
        lits = set(self.literals)
        for a in self.assumptions:
            if a not in lits:
                self.literals.append(a)
                lits.add(a)
            if a not in self.contrary:
                raise ABAError(f"Contraire manquant pour l'hypothèse '{a}'")
        for a, c in self.contrary.items():
            if a not in self.assumptions:
                raise ABAError(f"C({a}) défini mais '{a}' n'est pas une hypothèse")
            if c not in lits:
                self.literals.append(c)
                lits.add(c)
        heads = {r.head for r in self.rules}
        for a in self.assumptions:
            if a in heads:
                raise ABAError(
                    f"Cadre non plat : l'hypothèse '{a}' est la tête d'une règle")
        for r in self.rules:
            for s in (r.head, *r.body):
                if s not in lits:
                    self.literals.append(s)
                    lits.add(s)

    
    # Préférences
    def prefers(self, x, y):
        """True si x est strictement préférée à y."""
        return (x, y) in self.strict_pref

   
    # Conversion non circulaire + atomique (dépliage)
    def to_atomic(self):
        """
        Retourne un cadre ABA équivalent, non circulaire et atomique.

        Chaque règle dépliée a pour corps un ensemble d'hypothèses. Les
        dérivations circulaires (un littéral dérivé à partir de lui-même)
        sont ignorées. Les couples (support, conclusion) des arguments sont
        préservés.
        """
        A = set(self.assumptions)
        by_head = {}
        for r in self.rules:
            by_head.setdefault(r.head, []).append(r)

        def derive(s, visiting):
            if s in A:
                return [({s}, s)]
            if s in visiting:
                return []  # dérivation circulaire
            out = []
            for r in by_head.get(s, []):
                combos = [(set(), [])]
                for b in r.body:
                    opts = derive(b, visiting | {s})
                    combos = [(S | S2, ts + [t2])
                              for (S, ts) in combos for (S2, t2) in opts]
                    if not combos:
                        break
                for S, ts in combos:
                    tree = f"{r.id}({','.join(ts)})" if ts else r.id
                    out.append((S, tree))
            return out

        new_rules, n = [], 0
        for head in dict.fromkeys(r.head for r in self.rules):
            # clé du dictionnaire : tuple trié des hypothèses (un set n'est
            # pas hachable, donc il ne peut pas servir de clé)
            merged = {}
            for S, tree in derive(head, set()):
                merged.setdefault(tuple(sorted(S)), []).append(tree)
            for body, trees in merged.items():
                n += 1
                new_rules.append(Rule(f"u{n}", head, body, tuple(trees)))
        return ABA(self.literals, self.assumptions, self.contrary,
                   new_rules, self.strict_pref)

    def is_atomic(self):
        A = set(self.assumptions)
        return all(b in A for r in self.rules for b in r.body)

    # ------------------------------------------------------------------ #
    # Arguments (à appeler sur un cadre atomique)
    def arguments(self):
        if not self.is_atomic():
            raise ABAError("Les arguments se construisent sur un cadre atomique")
        args, i = [], 0
        for a in self.assumptions:
            i += 1
            args.append(Argument(f"A{i}", a, {a}, None))
        for r in self.rules:
            i += 1
            args.append(Argument(f"A{i}", r.head, set(r.body), r.id))
        return args

   
    # Attaques
    def attacks(self, args):
        """
        Retourne (plain, normal, reverse), chacune une liste de
        (attaquant, attaqué, hypothèse visée).

        plain   : attaques sans préférences.
        normal  : X attaque Y sur y si claim(X) = contraire(y), y in supp(Y)
                  et aucune hypothèse x de supp(X) n'est strictement moins
                  préférée que y.
        reverse : X attaque en retour Y s'il existe x in supp(X) avec
                  claim(Y) = contraire(x) et y' in supp(Y) avec y' < x
                  (l'attaque normale de Y sur x est bloquée).
        """
        plain, normal, reverse = [], [], []
        for X in args:
            for Y in args:
                for y in sorted(Y.support):
                    if self.contrary[y] != X.claim:
                        continue
                    plain.append((X, Y, y))
                    if not any(self.prefers(y, x) for x in X.support):
                        normal.append((X, Y, y))
                    else:
                        # attaque normale de X sur y bloquée -> attaque inverse
                        # de Y' (qui contient y) sur X, via les x moins préférées
                        pass
        for X in args:
            for Y in args:
                for x in sorted(X.support):
                    if self.contrary[x] == Y.claim and any(
                            self.prefers(x, y) for y in Y.support):
                        reverse.append((X, Y, x))
        return plain, normal, reverse



# Parsing
def _split(s):
    return [t.strip() for t in s.split(",") if t.strip()]


def _build_preferences(assumptions, chains):
    """chains : liste de listes de niveaux ; niveau = liste d'hypothèses égales."""
    A = set(assumptions)
    parent = {a: a for a in A}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for levels in chains:
        for lvl in levels:
            for x in lvl:
                if x not in A:
                    raise ABAError(f"Préférence sur '{x}' qui n'est pas une hypothèse")
            for x in lvl[1:]:
                parent[find(x)] = find(lvl[0])
    strict = set()
    for levels in chains:
        for i in range(len(levels)):
            for j in range(i + 1, len(levels)):
                for x in levels[i]:
                    for y in levels[j]:
                        strict.add((find(x), find(y)))
    changed = True
    while changed:  # fermeture transitive
        changed = False
        for (a, b), (c, d) in product(list(strict), list(strict)):
            if b == c and (a, d) not in strict:
                strict.add((a, d))
                changed = True
    if any(a == b for a, b in strict):
        raise ABAError("Préférences incohérentes (cycle)")
    return {(x, y) for x in A for y in A if (find(x), find(y)) in strict}


def parse(text):
    literals, assumptions, contraries, rules, chains = [], [], {}, [], []
    section = None
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("##"):
                section = line.lstrip("#").strip().lower()
            continue
        try:
            if m := re.fullmatch(r"L\s*:\s*\[(.*)\]", line):
                literals += _split(m.group(1))
            elif m := re.fullmatch(r"A\s*:\s*\[(.*)\]", line):
                assumptions += _split(m.group(1))
            elif m := re.fullmatch(r"C\(\s*([^\s()]+)\s*\)\s*:\s*(\S+)", line):
                contraries[m.group(1)] = m.group(2)
            elif m := re.fullmatch(r"\[([^\]]+)\]\s*:\s*([^\s,]+)\s*<-\s*(.*)", line):
                rules.append(Rule(m.group(1).strip(), m.group(2), tuple(_split(m.group(3)))))
            elif section and section.startswith("pref") or line.upper().startswith("PREF"):
                body = re.sub(r"^PREF\s*:", "", line, flags=re.I)
                chains.append([_split(lvl) for lvl in body.split(">")])
            else:
                raise ABAError("ligne non reconnue")
        except ABAError as e:
            raise ABAError(f"Ligne {no} ({raw.strip()!r}) : {e}") from None
    if not assumptions:
        raise ABAError("Aucune hypothèse définie (A: [...])")
    strict = _build_preferences(assumptions, chains)
    return ABA(literals, assumptions, contraries, rules, strict)



# Rapport
def generate(text):
    """Pipeline complet ; retourne (rapport texte, dict de résultats)."""
    fw = parse(text)
    atomic = fw.to_atomic()
    args = atomic.arguments()
    plain, normal, reverse = atomic.attacks(args)
    has_pref = bool(fw.strict_pref)

    out = []
    out.append("Cadre ABA d'origine ")
    out.append(f"Littéraux  : {', '.join(fw.literals)}")
    out.append(f"Hypothèses : {', '.join(fw.assumptions)}")
    out += [f"C({a}) = {fw.contrary[a]}" for a in fw.assumptions]
    out += [str(r) for r in fw.rules]
    if has_pref:
        out.append("Préférences (x > y) : " +
                   ", ".join(f"{x}>{y}" for x, y in sorted(fw.strict_pref)))

    out.append("\nCadre non circulaire et atomique ")
    for r in atomic.rules:
        out.append(f"{r}    (de {' | '.join(r.origins)})")
    if not atomic.rules:
        out.append("(aucune règle)")

    out.append("\n Les Arguments ")
    out += [str(a) for a in args]

    def fmt(lst):
        return [f"{x.name} -> {y.name}   (sur {h})" for x, y, h in lst] or ["(aucune)"]

    if not has_pref:
        out.append(" les  Attaques ")
        out += fmt(plain)
    else:
        out.append("\n les Attaques sans préférence ")
        out += fmt(plain)
        out.append("\nles Attaque normales")
        out += fmt(normal)
        out.append(" les Attaques inverses ")
        out += fmt(reverse)
        out.append("\n les  Attaques finales (normales + inverses) ")
        out += fmt(normal + reverse)

    return "\n".join(out), {
        "framework": fw, "atomic": atomic, "arguments": args,
        "plain": plain, "normal": normal, "reverse": reverse,
    }


if __name__ == "__main__":
    data = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    try:
        print(generate(data)[0])
    except ABAError as e:
        sys.exit(f"Erreur : {e}")
