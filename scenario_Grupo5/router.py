# -*- coding: utf-8 -*-

import csv
import json
import threading
import time
from argparse import ArgumentParser

import requests
from flask import Flask, jsonify, request

class Router:
    """
    Representa um roteador que executa o algoritmo de Vetor de DistÃ¢ncia.
    """

    def __init__(
        self,
        my_address,
        neighbors,
        my_network,
        update_interval=1,
        summarize_neighbors=None,
        poisoned_reverse=False,
        infinity_metric=16,
        route_timeout_cycles=3
    ):
        """
        Inicializa o roteador.

        :param my_address: O endereço (ip:porta) deste roteador.
        :param neighbors: Um dicionário contendo os vizinhos diretos e o custo do link.
                          Ex: {'127.0.0.1:5001': 5, '127.0.0.1:5002': 10}
        :param my_network: A rede que este roteador administra diretamente.
                           Ex: '10.0.1.0/24'
        :param update_interval: O intervalo em segundos para enviar atualizações, o tempo que o roteador espera
                               antes de enviar atualizações para os vizinhos.
        :param summarize_neighbors: Conjunto/lista de vizinhos para os quais os anúncios devem ser sumarizados.
        :param poisoned_reverse: Habilita o envio de rotas aprendidas de um vizinho com métrica infinita para ele.
        :param infinity_metric: Valor de métrica considerado "infinito" no poisoned reverse.
        :param route_timeout_cycles: Quantos ciclos sem update para considerar vizinho inativo.
        """
        self.my_address = my_address
        self.neighbors = neighbors
        self.my_network = my_network
        self.update_interval = update_interval
        self.summarize_neighbors = set(summarize_neighbors or [])
        self.poisoned_reverse = poisoned_reverse
        self.infinity_metric = int(infinity_metric)
        self.route_timeout_cycles = max(1, int(route_timeout_cycles))
        self.route_timeout_seconds = self.route_timeout_cycles * self.update_interval
        self.update_cycle = 0
        now = time.time()
        self.neighbor_last_seen = {neighbor: now for neighbor in self.neighbors}
        self.neighbors_down = set()

        self.routing_table = {
            self.my_network: {"cost": 0, "next_hop": self.my_network}
        }

        for neighbor_address, link_cost in self.neighbors.items():
            self.routing_table[neighbor_address] = {
                "cost": link_cost,
                "next_hop": neighbor_address
            }

        print("Tabela de roteamento inicial:")
        print(json.dumps(self.routing_table, indent=4))

        # Inicia o processo de atualização periódica em uma thread separada
        self._start_periodic_updates()

    def mark_neighbor_seen(self, neighbor_address):
        """Atualiza o timestamp de recebimento e recupera vizinho anteriormente inativo."""
        self.neighbor_last_seen[neighbor_address] = time.time()
        if neighbor_address in self.neighbors_down:
            self.neighbors_down.remove(neighbor_address)
            self.routing_table[neighbor_address] = {
                "cost": self.neighbors[neighbor_address],
                "next_hop": neighbor_address
            }
            print(
                f"[ciclo {self.update_cycle}] Vizinho {neighbor_address} voltou a responder; "
                "rota direta restaurada."
            )

    def _expire_stale_neighbors(self):
        """Invalida rotas de vizinhos sem atualização por tempo demais."""
        now = time.time()
        for neighbor_address in self.neighbors:
            last_seen = self.neighbor_last_seen.get(neighbor_address, now)
            if now - last_seen <= self.route_timeout_seconds:
                continue
            if neighbor_address in self.neighbors_down:
                continue

            self.neighbors_down.add(neighbor_address)
            self.routing_table[neighbor_address] = {
                "cost": self.infinity_metric,
                "next_hop": neighbor_address
            }

            changed = False
            for network, info in list(self.routing_table.items()):
                if network == self.my_network:
                    continue
                if not isinstance(info, dict):
                    continue
                if info.get("next_hop") != neighbor_address:
                    continue
                if int(info.get("cost", self.infinity_metric)) != self.infinity_metric:
                    info["cost"] = self.infinity_metric
                    self.routing_table[network] = info
                    changed = True

            timeout_cycles = int((now - last_seen) // self.update_interval)
            print(
                f"[ciclo {self.update_cycle}] Vizinho {neighbor_address} inativo por "
                f"{timeout_cycles} ciclos: rotas via ele marcadas com custo {self.infinity_metric}."
            )
            if changed:
                print("Tabela de roteamento após expiração:")
                print(json.dumps(self.routing_table, indent=4))

    def _start_periodic_updates(self):
        """Inicia uma thread para enviar atualizações periodicamente."""
        thread = threading.Thread(target=self._periodic_update_loop)
        thread.daemon = True
        thread.start()

    def _periodic_update_loop(self):
        """Loop que envia atualizações de roteamento em intervalos regulares."""
        while True:
            time.sleep(self.update_interval)
            self.update_cycle += 1
            self._expire_stale_neighbors()
            print(
                f"[{time.ctime()}] Enviando atualizações periódicas para os vizinhos... "
                f"(ciclo {self.update_cycle})"
            )
            try:
                self.send_updates_to_neighbors()
            except Exception as e:
                print(f"Erro durante a atualização periódica: {e}")

    def send_updates_to_neighbors(self):
        """
        Envia a tabela por vizinho:
        - detalhada para vizinhos comuns
        - sumarizada para vizinhos configurados em `self.summarize_neighbors`
        """
        def _ip_to_int(ip):
            a, b, c, d = ip.split('.')
            return (int(a) << 24) | (int(b) << 16) | (int(c) << 8) | int(d)

        def _int_to_ip(value):
            return f"{(value >> 24) & 255}.{(value >> 16) & 255}.{(value >> 8) & 255}.{value & 255}"

        def _parse_cidr(route):
            if ':' in route or '/' not in route:
                return None
            try:
                ip_part, prefix_part = route.split('/', 1)
                prefix = int(prefix_part)
                if prefix < 0 or prefix > 32:
                    return None
                mask = 0 if prefix == 0 else ((0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF)
                network_int = _ip_to_int(ip_part) & mask
                return network_int, prefix
            except (ValueError, AttributeError):
                return None

        tabela_detalhada = {}
        for destino, info in self.routing_table.items():
            if ":" in destino:
                continue
            if not isinstance(info, dict):
                continue
            if _parse_cidr(destino) is None:
                continue
            tabela_detalhada[destino] = info.copy()

        tabela_para_enviar = {
            destino: info.copy()
            for destino, info in tabela_detalhada.items()
        }

        grupos = {}
        for destino, info in tabela_detalhada.items():
            parsed = _parse_cidr(destino)
            if parsed is None:
                continue

            network_int, prefix = parsed
            next_hop = info.get("next_hop")
            raw_cost = info.get("cost")
            if next_hop is None or raw_cost is None:
                continue
            try:
                cost = int(raw_cost)
            except (ValueError, TypeError):
                continue

            grupos.setdefault((next_hop, prefix), []).append((destino, network_int, cost))

        # 1) Sumarização exata primeiro (mais segura): blocos contíguos, alinhados e potência de 2.
        for (next_hop, prefix), rotas in grupos.items():
            if prefix < 1:
                continue

            if len(rotas) < 2:
                continue

            step = 1 << (32 - prefix)
            rotas_ordenadas = sorted(rotas, key=lambda item: item[1])
            run_inicio = 0

            while run_inicio < len(rotas_ordenadas):
                run_fim = run_inicio
                while (
                    run_fim + 1 < len(rotas_ordenadas)
                    and rotas_ordenadas[run_fim + 1][1] - rotas_ordenadas[run_fim][1] == step
                ):
                    run_fim += 1

                run = rotas_ordenadas[run_inicio:run_fim + 1]
                i = 0
                while i < len(run):
                    inicio_bloco = run[i][1]
                    restantes = len(run) - i
                    bloco_len = 1

                    # Busca o maior bloco potência de 2, alinhado e sem criar /8 ou menor.
                    candidato = 1
                    while candidato * 2 <= restantes:
                        candidato *= 2

                    while candidato >= 2:
                        novo_prefixo = prefix - (candidato.bit_length() - 1)
                        if novo_prefixo < 9:
                            candidato //= 2
                            continue

                        bloco_tamanho_ips = candidato * step
                        if inicio_bloco % bloco_tamanho_ips == 0:
                            bloco_len = candidato
                            break
                        candidato //= 2

                    if bloco_len >= 2:
                        chunk = run[i:i + bloco_len]
                        novo_prefixo = prefix - (bloco_len.bit_length() - 1)
                        rede_sumarizada = f"{_int_to_ip(inicio_bloco)}/{novo_prefixo}"
                        custo_sumarizado = max(item[2] for item in chunk)

                        for destino_original, _, _ in chunk:
                            tabela_para_enviar.pop(destino_original, None)

                        tabela_para_enviar[rede_sumarizada] = {
                            "cost": custo_sumarizado,
                            "next_hop": next_hop
                        }
                        i += bloco_len
                    else:
                        i += 1

                run_inicio = run_fim + 1

        # 2) Sumarização relaxada (opcional) sobre o que sobrou após a etapa exata.
        for (next_hop, prefix), rotas in grupos.items():
            if prefix < 1 or len(rotas) < 2:
                continue

            # Só considera rotas ainda não resumidas na etapa exata.
            rotas_restantes = [
                (destino, network_int, cost)
                for destino, network_int, cost in rotas
                if destino in tabela_para_enviar
            ]
            if len(rotas_restantes) < 2:
                continue

            step = 1 << (32 - prefix)
            redes_unicas = sorted({item[1] for item in rotas_restantes})
            if len(redes_unicas) < 2:
                continue

            min_net = redes_unicas[0]
            max_net = redes_unicas[-1]
            max_end = max_net + step - 1

            xor_value = min_net ^ max_end
            summary_prefix = 32
            while xor_value:
                xor_value >>= 1
                summary_prefix -= 1

            if summary_prefix < 9:
                continue

            relax_bits = prefix - summary_prefix
            if relax_bits < 1:
                continue
            # Evita superdimensionar demais: permite até 4x os blocos base.
            if relax_bits > 2:
                continue

            summary_block_size = 1 << (32 - summary_prefix)
            summary_mask = (0xFFFFFFFF << (32 - summary_prefix)) & 0xFFFFFFFF
            summary_start = min_net & summary_mask
            total_slots = summary_block_size // step

            present_slots = sorted({(net - summary_start) // step for net in redes_unicas})
            if any(slot < 0 or slot >= total_slots for slot in present_slots):
                continue

            missing_slots = total_slots - len(present_slots)
            if missing_slots > 1:
                continue

            # Se houver 1 "buraco", ele só pode estar na borda, nunca no meio.
            if missing_slots == 1:
                all_slots = set(range(total_slots))
                missing_slot = (all_slots - set(present_slots)).pop()
                if missing_slot not in (0, total_slots - 1):
                    continue

            rede_sumarizada = f"{_int_to_ip(summary_start)}/{summary_prefix}"
            custo_sumarizado = max(item[2] for item in rotas_restantes)

            for destino_original, _, _ in rotas_restantes:
                tabela_para_enviar.pop(destino_original, None)

            tabela_para_enviar[rede_sumarizada] = {
                "cost": custo_sumarizado,
                "next_hop": next_hop
            }

        for neighbor_address in self.neighbors:
            tabela_base = tabela_para_enviar if neighbor_address in self.summarize_neighbors else tabela_detalhada
            tabela_do_vizinho = {
                destino: info.copy() if isinstance(info, dict) else info
                for destino, info in tabela_base.items()
            }

            if self.poisoned_reverse:
                for destino, info in tabela_do_vizinho.items():
                    if not isinstance(info, dict):
                        continue
                    if info.get("next_hop") == neighbor_address:
                        info["cost"] = self.infinity_metric

            payload = {
                "sender_address": self.my_address,
                "routing_table": tabela_do_vizinho
            }
            url = f'http://{neighbor_address}/receive_update'
            try:
                modo = "sumarizada" if neighbor_address in self.summarize_neighbors else "detalhada"
                print(f"Enviando tabela {modo} para {neighbor_address}")
                requests.post(url, json=payload, timeout=5)
            except requests.exceptions.RequestException as e:
                print(f"Não foi possível conectar ao vizinho {neighbor_address}. Erro: {e}")


# --- API Endpoints ---
# Instância do Flask e do Roteador (serão inicializadas no main)
app = Flask(__name__)
router_instance = None

@app.route('/routes', methods=['GET'])
def get_routes():
    """Endpoint para visualizar a tabela de roteamento atual."""
    if router_instance:
        return jsonify({
            "status": "success",
            "message": "Tabela de roteamento atual",
            "vizinhos" : router_instance.neighbors,
            "my_network": router_instance.my_network,
            "my_address": router_instance.my_address,
            "update_interval": router_instance.update_interval,
            "update_cycle": router_instance.update_cycle,
            "route_timeout_cycles": router_instance.route_timeout_cycles,
            "neighbors_down": sorted(router_instance.neighbors_down),
            "summarize_neighbors": sorted(router_instance.summarize_neighbors),
            "routing_table": router_instance.routing_table
        })
    return jsonify({"error": "Roteador não inicializado"}), 500


@app.route('/receive_update', methods=['POST'])
def receive_update():
    """Endpoint que recebe atualizações de roteamento de um vizinho."""
    
    if not request.json:
        return jsonify({"error": "Invalid request"}), 400

    update_data = request.json
    sender_address = update_data.get("sender_address")
    sender_table = update_data.get("routing_table")

    if not sender_address or not isinstance(sender_table, dict):
        return jsonify({"error": "Missing sender_address or routing_table"}), 400

    print(f"Recebida atualização de {sender_address}:")
    print(json.dumps(sender_table, indent=4))

    if sender_address not in router_instance.neighbors:
        return jsonify({"error": "Unknown neighbor"}), 400

    router_instance.mark_neighbor_seen(sender_address)
    link_cost = router_instance.neighbors[sender_address]
    changed = False

    for network, info in sender_table.items():
        if network == router_instance.my_network:
            continue
        if ":" in network:
            continue
        if not isinstance(info, dict):
            continue
        if "cost" not in info or "next_hop" not in info:
            continue

        try:
            reported_cost = int(info["cost"])
        except (ValueError, TypeError):
            continue

        new_cost = link_cost + reported_cost
        current = router_instance.routing_table.get(network)

        if current is None:
            router_instance.routing_table[network] = {
                "cost": new_cost,
                "next_hop": sender_address
            }
            changed = True
        else:
            current_cost = current.get("cost")
            current_next = current.get("next_hop")

            if (current_cost is None) or (new_cost < current_cost) or (current_next == sender_address):
                if current_cost != new_cost or current_next != sender_address:
                    router_instance.routing_table[network] = {
                        "cost": new_cost,
                        "next_hop": sender_address
                    }
                    changed = True

    if changed:
        print("Tabela de roteamento ATUALIZADA:")
        print(json.dumps(router_instance.routing_table, indent=4))

    # TODO: Implemente a lógica de Bellman-Ford aqui.
    #
    # 1. Verifique se o remetente é um vizinho conhecido.
    # 2. Obtenha o custo do link direto para este vizinho a partir de `router_instance.neighbors`.
    # 3. Itere sobre cada rota (`network`, `info`) na `sender_table` recebida.
    # 4. Calcule o novo custo para chegar à `network`:
    #    novo_custo = custo_do_link_direto + info['cost']
    # 5. Verifique sua própria tabela de roteamento:
    #    a. Se você não conhece a `network`, adicione-a à sua tabela com o
    #       `novo_custo` e o `next_hop` sendo o `sender_address`.
    #    b. Se você já conhece a `network`, verifique se o `novo_custo` é menor
    #       que o custo que você já tem. Se for, atualize sua tabela com o
    #       novo custo e o novo `next_hop`.
    #    c. (Opcional, mas importante para robustez): Se o `next_hop` para uma rota
    #       for o `sender_address`, você deve sempre atualizar o custo, mesmo que
    #       seja maior (isso ajuda a propagar notícias de links quebrados).
    #
    # 6. Mantenha um registro se sua tabela mudou ou não. Se mudou, talvez seja
    #    uma boa ideia imprimir a nova tabela no console.

    

    return jsonify({"status": "success", "message": "Update received"}), 200

if __name__ == '__main__':

    parser = ArgumentParser(description="Simulador de Roteador - Topologia 12 Roteadores")
    parser.add_argument('router_name', type=str, help="Nome do roteador (R1 ... R12)")
    args = parser.parse_args()

    router_name = args.router_name

    # ----------------------------
    # Ler topologia.json
    # ----------------------------
    try:
        with open("topologia.json") as f:
            topology = json.load(f)
    except Exception as e:
        print("Erro ao abrir topologia.json:", e)
        exit(1)

    router_info = None
    for r in topology:
        if r["name"] == router_name:
            router_info = r
            break

    if router_info is None:
        print("Roteador não encontrado no topologia.json")
        exit(1)

    my_network = router_info["network"]
    address = router_info["address"]
    csv_file = router_info["config_file"]

    host = address.split(":")[0]
    port = int(address.split(":")[1])

    # ----------------------------
    # Ler CSV de vizinhos
    # ----------------------------
    neighbors_config = {}

    try:
        with open(csv_file) as infile:
            reader = csv.DictReader(infile)

            for row in reader:
                neighbors_config[row["vizinho"]] = int(row["custo"])

    except Exception as e:
        print("Erro ao ler CSV:", e)
        exit(1)

    # ----------------------------
    # Inicialização
    # ----------------------------

    my_full_address = address

    print("====================================")
    print("Iniciando Roteador", router_name)
    print("Endereço:", my_full_address)
    print("Rede Local:", my_network)
    print("Vizinhos:", neighbors_config)
    print("====================================")

    router_instance = Router(
        my_address=my_full_address,
        neighbors=neighbors_config,
        my_network=my_network,
        update_interval=2,
        summarize_neighbors=[],
        poisoned_reverse=False,
        infinity_metric=16,
        route_timeout_cycles=3
    )

    app.run(host="0.0.0.0", port=port, debug=False)