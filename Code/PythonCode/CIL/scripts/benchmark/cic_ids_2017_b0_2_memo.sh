python3.9 main_memo.py \
    -model memo_kdd \
    -init 2 \
    -incre 2 \
    -net cic_ids_memo_ann \
    --dataset cic-ids-2017 \
    --train_base \
    --scheduler steplr \
    --init_epoch 50 \
    --epochs 50 \
    --batch_size 128 \
    -d -1