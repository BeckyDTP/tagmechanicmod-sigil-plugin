pylupdate5 -verbose -translate-function _t dialogs.py -ts ./translations/template.ts
pylupdate5 -verbose -translate-function _t dialogs.py -ts ./translations/tagmechanicmod_pl.ts
lconvert.exe -i ./translations/tagmechanicmod_pl.ts -o ./translations/tagmechanicmod_pl.qm -if ts -of qm
