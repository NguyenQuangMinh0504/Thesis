python3 main.py \
    -model der \
    --dataset kdd99 \
    -net kdd_dnn \
    -init 2 \
    -incre 2 \
    -p benchmark \
    -d -1 \
    --init_epoch 300 \
    --epochs 300 \
    --batch_size 128 \
    --pre_processing min_max_scale 

