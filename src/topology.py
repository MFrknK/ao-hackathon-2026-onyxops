"""Gorev 1.2 — Servis bagimlilik grafigi.

32 kenarlik bir grafik icin harici bir kutuphane (networkx) tasimak yerine
ihtiyacimiz olan dort islemi kendimiz yaziyoruz:

  * `dependents_of`   : X bozulursa dogrudan kim etkilenir
  * `impact_set`      : X bozulursa k atlamaya kadar kim etkilenir
  * `hop_distance`    : iki servis arasi yonsuz mesafe (kume birlestirme icin)
  * `centrality`      : X'in kac servisin altinda yattigi (kok neden puani)

Okuma yonu (veri sozlugu): `kaynak_servis` -> `hedef_servis` kenari
"kaynak, hedefe bagimlidir" demektir. Dolayisiyla **etki**, hedeften kaynaga
dogru, yani kenarin tersine akar.
"""

from __future__ import annotations

from collections import defaultdict, deque

from src.models import Dependency


class DependencyGraph:
    """Servisler arasi yonlu bagimlilik grafigi."""

    def __init__(self, dependencies: list[Dependency], services: set[str] | None = None):
        self.dependencies = list(dependencies)

        self.services: set[str] = set(services or set())
        for dep in self.dependencies:
            self.services.add(dep.source)
            self.services.add(dep.target)

        # kaynak -> bagimli oldugu hedefler  (asagi dogru: "neye guveniyorum")
        self._depends_on: dict[str, set[str]] = defaultdict(set)
        # hedef -> ona bagimli olan kaynaklar (yukari dogru: "beni kim kullaniyor")
        self._dependents: dict[str, set[str]] = defaultdict(set)
        # yonsuz komsuluk (mesafe hesaplari icin)
        self._neighbors: dict[str, set[str]] = defaultdict(set)

        self._edge_meta: dict[tuple[str, str], Dependency] = {}

        for dep in self.dependencies:
            self._depends_on[dep.source].add(dep.target)
            self._dependents[dep.target].add(dep.source)
            self._neighbors[dep.source].add(dep.target)
            self._neighbors[dep.target].add(dep.source)
            self._edge_meta[(dep.source, dep.target)] = dep

        self._centrality_cache: dict[str, float] = {}

    # ---------------------------------------------------------------- temel

    def __len__(self) -> int:
        return len(self.services)

    @property
    def edge_count(self) -> int:
        return len(self.dependencies)

    def depends_on(self, service: str) -> set[str]:
        """`service`'in dogrudan bagimli oldugu servisler."""
        return set(self._depends_on.get(service, set()))

    def dependents_of(self, service: str) -> set[str]:
        """`service` bozulursa dogrudan etkilenecek servisler."""
        return set(self._dependents.get(service, set()))

    def edge(self, source: str, target: str) -> Dependency | None:
        return self._edge_meta.get((source, target))

    # ------------------------------------------------------------- yayilim

    def impact_set(self, service: str, max_hops: int = 3) -> dict[str, int]:
        """`service` bozulursa etkilenecek servisler -> kacinci atlamada.

        Kenarlarin tersi yonunde (hedef -> kaynak) genisletilmis BFS.
        """
        seen: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(service, 0)])
        while queue:
            node, hop = queue.popleft()
            if hop >= max_hops:
                continue
            for dependent in sorted(self._dependents.get(node, set())):
                if dependent == service or dependent in seen:
                    continue
                seen[dependent] = hop + 1
                queue.append((dependent, hop + 1))
        return seen

    def upstream_set(self, service: str, max_hops: int = 3) -> dict[str, int]:
        """`service`'in (gecisli olarak) bagimli oldugu servisler.

        Bu kumedeki bir servisin bozulmasi `service`'te semptom uretir; kok
        neden aramasinda "yukari bak" tarafidir.
        """
        seen: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(service, 0)])
        while queue:
            node, hop = queue.popleft()
            if hop >= max_hops:
                continue
            for target in sorted(self._depends_on.get(node, set())):
                if target == service or target in seen:
                    continue
                seen[target] = hop + 1
                queue.append((target, hop + 1))
        return seen

    def hop_distance(self, a: str, b: str, max_hops: int = 3) -> int | None:
        """Yonsuz en kisa mesafe; `max_hops` icinde bulunamazsa None."""
        if a == b:
            return 0
        seen = {a}
        queue: deque[tuple[str, int]] = deque([(a, 0)])
        while queue:
            node, hop = queue.popleft()
            if hop >= max_hops:
                continue
            for nb in sorted(self._neighbors.get(node, set())):
                if nb in seen:
                    continue
                if nb == b:
                    return hop + 1
                seen.add(nb)
                queue.append((nb, hop + 1))
        return None

    def are_related(self, a: str, b: str, max_hops: int = 2) -> tuple[bool, str]:
        """Iki servis bagimlilik acisindan yakin mi? Gerekcesiyle birlikte."""
        dist = self.hop_distance(a, b, max_hops=max_hops)
        if dist is None:
            return False, ""
        if dist == 0:
            return True, "ayni servis"
        if b in self._depends_on.get(a, set()):
            return True, f"{a} dogrudan {b} servisine bagimli"
        if a in self._depends_on.get(b, set()):
            return True, f"{b} dogrudan {a} servisine bagimli"
        return True, f"bagimlilik grafiginde {dist} atlama mesafesinde"

    # ---------------------------------------------------------- merkezilik

    def centrality(self, service: str) -> float:
        """0-1 arasi topolojik merkezilik.

        1 atlama uzaktaki bagimlilar tam, 2 atlama uzaktakiler yarim, 3 atlama
        uzaktakiler ceyrek agirlikla sayilir; toplam servis sayisina bolunur.
        Yalnizca servisin **altinda** yatan bagimlilik yuku olculur — cok
        servisin dayandigi bir servis, kok neden olmaya daha yatkindir.
        """
        if service in self._centrality_cache:
            return self._centrality_cache[service]

        decay = {1: 1.0, 2: 0.5, 3: 0.25}
        impact = self.impact_set(service, max_hops=3)
        raw = sum(decay.get(hop, 0.0) for hop in impact.values())

        # Normalizasyon: en yuksek ham degeri 1.0 kabul et.
        denominator = max(1.0, self._max_raw_centrality())
        value = min(1.0, raw / denominator)
        self._centrality_cache[service] = value
        return value

    def _max_raw_centrality(self) -> float:
        if not hasattr(self, "_max_raw"):
            decay = {1: 1.0, 2: 0.5, 3: 0.25}
            values = []
            for svc in sorted(self.services):
                impact = self.impact_set(svc, max_hops=3)
                values.append(sum(decay.get(h, 0.0) for h in impact.values()))
            self._max_raw = max(values) if values else 1.0
        return self._max_raw

    def describe(self, service: str) -> str:
        """Kanit metinlerinde kullanilan kisa topoloji ozeti."""
        direct = sorted(self.dependents_of(service))
        total = len(self.impact_set(service, max_hops=3))
        if not direct:
            return f"{service} servisine dogrudan bagimli baska servis yok (yaprak)"
        head = ", ".join(direct[:3]) + ("..." if len(direct) > 3 else "")
        return (
            f"{service} servisine {len(direct)} servis dogrudan bagimli ({head}); "
            f"gecisli etki alani {total} servis"
        )

    def to_dict(self) -> dict:
        """Panoda gosterim ve JSON cikti icin duz temsil."""
        return {
            "services": sorted(self.services),
            "edges": [
                {
                    "kaynak_servis": d.source,
                    "hedef_servis": d.target,
                    "bagimlilik_tipi": d.kind,
                    "kritiklik": d.criticality,
                }
                for d in self.dependencies
            ],
            "centrality": {
                svc: round(self.centrality(svc), 4) for svc in sorted(self.services)
            },
        }
