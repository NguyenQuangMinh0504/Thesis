python3 main.py \
    -model lwf \
    --dataset cic-ids-2017 \
    -ms 2000 \
    -init 2 \
    -incre 2 \
    -net cic_ids_ann \
    -p benchmark \
    --init_epoch 300 \
    --epochs 300 \
    --batch_size 128 \
    -d -1