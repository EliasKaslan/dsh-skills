#!/usr/bin/env python3
"""WCAG sRGB solid-color text contrast arithmetic; no browser/page compliance claim."""
import argparse,json,math,sys

def rgb(hex_color):
    if not isinstance(hex_color,str) or len(hex_color)!=7 or not hex_color.startswith('#'):
        raise ValueError('use #RRGGBB sRGB colors')
    try:return tuple(int(hex_color[i:i+2],16)/255 for i in (1,3,5))
    except ValueError:raise ValueError('invalid hex color') from None

def alpha(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
        raise ValueError('alpha must be finite in [0,1]')
    return value

def composite(fg,bg,opacity):
    opacity=alpha(opacity)
    return tuple(a*opacity+b*(1-opacity) for a,b in zip(fg,bg))

def luminance(color):
    lin=[x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4 for x in color]
    return sum(c*w for c,w in zip(lin,(0.2126,0.7152,0.0722)))

def ratio(fg,bg):
    light,dark=sorted((luminance(fg),luminance(bg)),reverse=True)
    return (light+0.05)/(dark+0.05)

def evaluate(foreground,background,font_px=16,bold=False,foreground_alpha=1,background_alpha=1,canvas='#ffffff'):
    if isinstance(font_px,bool) or not isinstance(font_px,(int,float)) or not math.isfinite(font_px) or font_px<=0:
        raise ValueError('font size must be positive finite CSS pixels')
    if type(bold) is not bool:raise ValueError('bold must be boolean')
    bg=composite(rgb(background),rgb(canvas),background_alpha)
    fg=composite(rgb(foreground),bg,foreground_alpha)
    contrast=ratio(fg,bg);large=font_px>=24 or (bold and font_px>=14*96/72)
    threshold=3 if large else 4.5
    return {'contrast_ratio':contrast,'threshold':threshold,'large_text':large,'passes_solid_text_threshold':contrast>=threshold,
            'effective_foreground_rgb':fg,'effective_background_rgb':bg,
            'scope':'single solid sRGB layer arithmetic; actual font, gradients, images, blending and page conformance not verified'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('foreground');p.add_argument('background')
    p.add_argument('--font-px',type=float,default=16);p.add_argument('--bold',action='store_true')
    p.add_argument('--foreground-alpha',type=float,default=1);p.add_argument('--background-alpha',type=float,default=1);p.add_argument('--canvas',default='#ffffff')
    args=p.parse_args(argv)
    try:result=evaluate(args.foreground,args.background,args.font_px,args.bold,args.foreground_alpha,args.background_alpha,args.canvas)
    except (ValueError,TypeError) as exc:print(json.dumps({'verdict':'ERROR','error':str(exc)}));return 2
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':sys.exit(main())
