    python3 main.py \
        -model der \
        --dataset cic-ids-2017 \
        -net cic_ids_ann \
        -init 2 \
        -incre 2 \
        -p benchmark \
        -d -1 \
        --init_epoch 300 \
        --epochs 300 \
        --batch_size 128