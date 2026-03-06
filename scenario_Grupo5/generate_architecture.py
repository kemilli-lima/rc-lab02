import matplotlib.pyplot as plt


def main():
    positions = {
        "R1\n10.0.1.0/24": (0, 2.0),
        "R2\n10.0.2.0/24": (-3, 3.2),
        "R3\n10.0.3.0/24": (-1.5, 3.2),
        "R4\n10.0.4.0/24": (0, 3.2),
        "R5\n10.0.5.0/24": (1.5, 3.2),
        "R6\n10.0.6.0/24": (3, 3.2),
        "R7\n10.0.7.0/24": (0, 5.0),
        "R8\n10.0.8.0/24": (-3, 6.2),
        "R9\n10.0.9.0/24": (-1.5, 6.2),
        "R10\n10.0.10.0/24": (0, 6.2),
        "R11\n10.0.11.0/24": (1.5, 6.2),
        "R12\n10.0.12.0/24": (3, 6.2),
    }

    edges = [
        ("R1\n10.0.1.0/24", "R2\n10.0.2.0/24", 1),
        ("R1\n10.0.1.0/24", "R3\n10.0.3.0/24", 2),
        ("R1\n10.0.1.0/24", "R4\n10.0.4.0/24", 3),
        ("R1\n10.0.1.0/24", "R5\n10.0.5.0/24", 2),
        ("R1\n10.0.1.0/24", "R6\n10.0.6.0/24", 1),
        ("R1\n10.0.1.0/24", "R7\n10.0.7.0/24", 4),
        ("R7\n10.0.7.0/24", "R8\n10.0.8.0/24", 1),
        ("R7\n10.0.7.0/24", "R9\n10.0.9.0/24", 2),
        ("R7\n10.0.7.0/24", "R10\n10.0.10.0/24", 3),
        ("R7\n10.0.7.0/24", "R11\n10.0.11.0/24", 2),
        ("R7\n10.0.7.0/24", "R12\n10.0.12.0/24", 1),
    ]

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_facecolor("#111827")
    fig.patch.set_facecolor("#111827")

    for node, (x, y) in positions.items():
        ax.text(
            x,
            y,
            node,
            ha="center",
            va="center",
            color="white",
            fontsize=11,
            bbox=dict(boxstyle="round,pad=0.45", fc="#1f2937", ec="#3b82f6", lw=2),
        )

    for n1, n2, cost in edges:
        x1, y1 = positions[n1]
        x2, y2 = positions[n2]
        ax.plot([x1, x2], [y1, y2], color="#cbd5e1", lw=1.8)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx, my + 0.12, str(cost), color="#f59e0b", fontsize=10, ha="center")

    ax.set_title(
        "Topologia Grupo 5 - Duas Estrelas Conectadas",
        color="white",
        fontsize=14,
        pad=12,
    )
    ax.set_xlim(-4, 4)
    ax.set_ylim(1.2, 7.0)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig("architecture.png", dpi=160)


if __name__ == "__main__":
    main()
