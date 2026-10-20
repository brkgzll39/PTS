"""PTS başlatıcı: `python pts_baslat.py` (kaynak ve derlenmiş kurulumda aynı).

Derlenmiş kurulumda backend tek bir derlenmiş modüldür (backend.*.pyd) ve
`python -m backend.sunucu` ile başlatılamaz; bu dosya her iki durumda çalışır.
"""
from backend.sunucu import main

if __name__ == "__main__":
    main()
