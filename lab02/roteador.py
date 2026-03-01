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

    def __init__(self, my_address, neighbors, my_network, update_interval=1, summarize_neighbors=None):
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
        """
        self.my_address = my_address
        self.neighbors = neighbors
        self.my_network = my_network
        self.update_interval = update_interval
        self.summarize_neighbors = set(summarize_neighbors or [])

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

    def _start_periodic_updates(self):
        """Inicia uma thread para enviar atualizações periodicamente."""
        thread = threading.Thread(target=self._periodic_update_loop)
        thread.daemon = True
        thread.start()

    def _periodic_update_loop(self):
        """Loop que envia atualizações de roteamento em intervalos regulares."""
        while True:
            time.sleep(self.update_interval)
            print(f"[{time.ctime()}] Enviando atualizações periódicas para os vizinhos...")
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
            cost = info.get("cost")
            if next_hop is None or cost is None:
                continue

            grupos.setdefault((next_hop, prefix), []).append((destino, network_int, cost))

        for (next_hop, prefix), rotas in grupos.items():
            if prefix < 1:
                continue

            if len(rotas) < 2:
                continue

            # Para um prefixo fixo, cada rota ocupa blocos de mesmo tamanho.
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

        for neighbor_address in self.neighbors:
            tabela_do_vizinho = tabela_para_enviar if neighbor_address in self.summarize_neighbors else tabela_detalhada
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

    link_cost = router_instance.neighbors[sender_address]
    changed = False

    for network, info in sender_table.items():
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
    parser = ArgumentParser(description="Simulador de Roteador com Vetor de Distância")
    parser.add_argument('-p', '--port', type=int, default=5000, help="Porta para executar o roteador.")
    parser.add_argument('-f', '--file', type=str, required=True, help="Arquivo CSV de configuração de vizinhos.")
    parser.add_argument('--network', type=str, required=True, help="Rede administrada por este roteador (ex: 10.0.1.0/24).")
    parser.add_argument('--interval', type=int, default=10, help="Intervalo de atualização periódica em segundos.")
    parser.add_argument(
        '--summarize-neighbors',
        type=str,
        default='',
        help="Lista de vizinhos (ip:porta) separados por vírgula para receber anúncios sumarizados."
    )
    args = parser.parse_args()

    # Leitura do arquivo de configuração de vizinhos
    neighbors_config = {}
    try:
        with open(args.file, mode='r') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                neighbors_config[row['vizinho']] = int(row['custo'])
    except FileNotFoundError:
        print(f"Erro: Arquivo de configuração '{args.file}' não encontrado.")
        exit(1)
    except (KeyError, ValueError) as e:
        print(f"Erro no formato do arquivo CSV: {e}. Verifique as colunas 'vizinho' e 'custo'.")
        exit(1)

    my_full_address = f"127.0.0.1:{args.port}"
    summarize_neighbors = {
        neighbor.strip()
        for neighbor in args.summarize_neighbors.split(',')
        if neighbor.strip()
    }
    print("--- Iniciando Roteador ---")
    print(f"Endereço: {my_full_address}")
    print(f"Rede Local: {args.network}")
    print(f"Vizinhos Diretos: {neighbors_config}")
    print(f"Intervalo de atualização: {args.interval}s")
    print(f"Vizinhos com sumarização: {sorted(summarize_neighbors)}")
    print("--------------------------")

    router_instance = Router(
        my_address=my_full_address,
        neighbors=neighbors_config,
        my_network=args.network,
        update_interval=args.interval,
        summarize_neighbors=summarize_neighbors
    )

    # Inicia o servidor Flask
    app.run(host='0.0.0.0', port=args.port, debug=False)
