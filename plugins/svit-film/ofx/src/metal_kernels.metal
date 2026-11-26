// Svit Film — Metal-ядра. Перед цим файлом під час збірки вставляється gpu_shared.h (той самий код,
// що перевіряється тестами на процесорі). Кожне ядро — тонка обгортка над функцією з gpu_shared.h.

kernel void k_stage1(device const float* src [[buffer(0)]], device float* lin [[buffer(1)]],
                     device const float* T [[buffer(2)]], constant KParams& k [[buffer(3)]],
                     uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= k.w || y >= k.h) return;
    float o[3];
    stage1G(src, T, k, x, y, o);
    int q = (y * k.w + x) * 3;
    lin[q] = o[0]; lin[q + 1] = o[1]; lin[q + 2] = o[2];
}

kernel void k_final(device const float* src [[buffer(0)]], device float* dst [[buffer(1)]],
                    device const float* lin [[buffer(2)]], device const float* T [[buffer(3)]],
                    constant KParams& k [[buffer(4)]], device const float* halo [[buffer(5)]],
                    uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= k.w || y >= k.h) return;
    float L[3], hp[3], res[4];
    hp[0] = 0.0f; hp[1] = 0.0f; hp[2] = 0.0f;
    int q = (y * k.w + x) * 3;
    if (k.needFrame != 0) { L[0] = lin[q]; L[1] = lin[q + 1]; L[2] = lin[q + 2]; }
    else stage1G(src, T, k, x, y, L);
    if (k.maskOn != 0) { hp[0] = halo[q]; hp[1] = halo[q + 1]; hp[2] = halo[q + 2]; }
    finalG(src, T, k, x, y, L, hp, res);
    int d = y * k.dstRow + x * 4;
    dst[d] = res[0]; dst[d + 1] = res[1]; dst[d + 2] = res[2]; dst[d + 3] = res[3];
}

kernel void k_blurH(device const float* inb [[buffer(0)]], device float* outb [[buffer(1)]],
                    device const float* wts [[buffer(2)]], constant BlurP& p [[buffer(3)]],
                    uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= p.w || y >= p.h) return;
    blurHG(inb, outb, wts, p, x, y);
}

kernel void k_blurV(device const float* inb [[buffer(0)]], device float* outb [[buffer(1)]],
                    device const float* wts [[buffer(2)]], constant BlurP& p [[buffer(3)]],
                    uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= p.w || y >= p.h) return;
    blurVG(inb, outb, wts, p, x, y);
}

kernel void k_down(device const float* lin [[buffer(0)]], device float* outb [[buffer(1)]],
                   constant DownP& p [[buffer(2)]], uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= p.ow || y >= p.oh) return;
    downG(lin, outb, p, x, y);
}

kernel void k_down2(device const float* inb [[buffer(0)]], device float* outb [[buffer(1)]],
                    constant Down2P& p [[buffer(2)]], uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= p.ow || y >= p.oh) return;
    down2G(inb, outb, p, x, y);
}

kernel void k_zero(device float* b [[buffer(0)]], constant Down2P& p [[buffer(1)]],
                   uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= p.ow || y >= p.oh) return;
    int q = (y * p.ow + x) * 3;
    b[q] = 0.0f; b[q + 1] = 0.0f; b[q + 2] = 0.0f;
}

kernel void k_accum(device const float* b [[buffer(0)]], device float* acc [[buffer(1)]],
                    constant AccP& p [[buffer(2)]], uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= p.aw || y >= p.ah) return;
    accumG(b, acc, p, x, y);
}

kernel void k_halApply(device float* lin [[buffer(0)]], device const float* acc [[buffer(1)]],
                       device float* halo [[buffer(2)]], constant KParams& k [[buffer(3)]],
                       uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= k.w || y >= k.h) return;
    halApplyG(lin, acc, halo, k, x, y);
}

kernel void k_bloomMix(device float* lin [[buffer(0)]], device const float* b [[buffer(1)]],
                       constant KParams& k [[buffer(2)]], uint2 gid [[thread_position_in_grid]]) {
    int x = (int)gid.x, y = (int)gid.y;
    if (x >= k.w || y >= k.h) return;
    bloomMixG(lin, b, k, x, y);
}
