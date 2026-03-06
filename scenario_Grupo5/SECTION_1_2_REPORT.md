# Seção 1.2 - Projeto de Cenário Complexo (Grupo 5 - Star)

## 1) Visão geral da topologia

A topologia foi organizada em **duas estrelas distintas conectadas entre si**:

- **Estrela A (centro R1)**: R1 conectado a R2, R3, R4, R5, R6.
- **Estrela B (centro R7)**: R7 conectado a R8, R9, R10, R11, R12.
- **Conexão entre estrelas**: enlace R1 <-> R7.

Essa organização atende ao requisito do README para Grupo 5:
"Os grupos responsáveis pela topologia em estrela deverão configurar no mínimo duas estruturas em estrela distintas, podendo conectá-las entre si."

## 2) Endereçamento e redes dos roteadores

| Roteador | Address | Rede administrada |
|---|---|---|
| R1 | 127.0.0.1:5001 | 10.0.1.0/24 |
| R2 | 127.0.0.1:5002 | 10.0.2.0/24 |
| R3 | 127.0.0.1:5003 | 10.0.3.0/24 |
| R4 | 127.0.0.1:5004 | 10.0.4.0/24 |
| R5 | 127.0.0.1:5005 | 10.0.5.0/24 |
| R6 | 127.0.0.1:5006 | 10.0.6.0/24 |
| R7 | 127.0.0.1:5007 | 10.0.7.0/24 |
| R8 | 127.0.0.1:5008 | 10.0.8.0/24 |
| R9 | 127.0.0.1:5009 | 10.0.9.0/24 |
| R10 | 127.0.0.1:5010 | 10.0.10.0/24 |
| R11 | 127.0.0.1:5011 | 10.0.11.0/24 |
| R12 | 127.0.0.1:5012 | 10.0.12.0/24 |

## 3) Enlaces e custos

### Estrela A (R1)
- R1-R2: 1
- R1-R3: 2
- R1-R4: 3
- R1-R5: 2
- R1-R6: 1

### Interligação das estrelas
- R1-R7: 4

### Estrela B (R7)
- R7-R8: 1
- R7-R9: 2
- R7-R10: 3
- R7-R11: 2
- R7-R12: 1

## 4) Arquivos do cenário

- `topologia.json`
- `R1.csv` ... `R12.csv`
- `architecture.png`
- `captura.pcap`

Arquivos de evidência adicionais da execução:
- `routes_initial_R1.json`
- `routes_final_R1.json`
- `logs/*.log`

## 5) Metodologia de execução e captura

Foi usado o script `run_scenario.py`, que:

1. Inicia os 12 roteadores (`router.py R1` ... `router.py R12`).
2. Aguarda estabilização inicial e coleta `routes_initial_R1.json`.
3. Mantém o cenário em execução para convergência.
4. Coleta `routes_final_R1.json`.
5. Encerra processos e gera `captura.pcap` com os eventos de atualização observados.

Comando executado:

```bash
python run_scenario.py
```

## 6) Resultado observado para convergência

No roteador R1:

- Snapshot inicial coletado em `update_cycle = 3`.
- Snapshot final coletado em `update_cycle = 12`.
- A tabela final permanece estável e contém as redes dos 12 roteadores.

Referências:
- `routes_initial_R1.json`
- `routes_final_R1.json`

## 7) Observações para entrega

- Para execução local nesta máquina, foi usado loopback (`127.0.0.1`) e portas distintas.
- Se o professor exigir estritamente o formato final de endereçamento descrito no README para entrega, adapte `address`/CSVs para o padrão solicitado antes do envio final.
