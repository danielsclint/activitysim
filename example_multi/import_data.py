# Convert SANDAG network los files to ActivitySim NetworkLOS format
# Ben Stabler, ben.stabler@rsginc.com, 02/03/17

import sys, os.path, openmatrix
import pandas as pd, numpy as np

############################################################
# paramaters
############################################################

# settings
folder = "/Users/jeff.doyle/work/activitysim-data/sandag_zone/"
output_folder = "/Users/jeff.doyle/work/activitysim-data/sandag_zone/output/"
outputDataStoreFileName = "NetworkData.h5"
outputBikeLogsumMatrixFileName = "bikelogsum.omx"

"""
    TAZ - there are 4997 TAZs with ids 1..4996
    MAZ - there are 2302 MAZs with ids 1..2302
    TAP - there are 1754 TAPs with ids 1..2498
"""
if __name__ == "__main__":



    # read CSVs and convert to NetworkLOS format
    # https://github.com/UDST/activitysim/wiki/Multiple-Zone-Systems-Design
    bikeMgraLogsum = pd.read_csv(folder + "bikeMgraLogsum.csv")
    walkMgraTapEquivMinutes = pd.read_csv(folder + "walkMgraTapEquivMinutes.csv")
    walkMgraEquivMinutes = pd.read_csv(folder + "walkMgraEquivMinutes.csv")
    mgra13_based_input2012 = pd.read_csv(folder + "mgra13_based_input2012.csv")
    Accessam = pd.read_csv(folder + "Accessam.csv")
    Tap_ptype = pd.read_csv(folder + "Tap_ptype.csv")
    Zone_term = pd.read_csv(folder + "Zone_term.csv")
    Zone_park = pd.read_csv(folder + "Zone_park.csv")

    # read taz and tap skim to get zone ids
    with openmatrix.open_file(folder + "impdan_AM.omx") as taz_skim:
        taz_numbers = taz_skim.mapping("Origin").keys()  # keys() shouldn't be needed?

    with openmatrix.open_file(folder + "implocl_AM.omx") as tap_skim:
        tap_numbers = tap_skim.mapping("RCIndex").keys()  # keys() shouldn't be needed?

    #
    # taz_skim_files = ['impdan_AM.omx', 'impdat_AM.omx', 'Trip_AM.omx']
    # tap_skim_files = ['implocl_AM.omx', 'implocl_AMo.omx', 'impprem_AM.omx', 'impprem_AMo.omx',
    #                   'tranTotalTrips_AM.omx', ]
    # for f in taz_skim_files+tap_skim_files:
    #     with openmatrix.open_file(folder + f) as s:
    #         print "%s shape %s mappings" % (f, s.shape()), s.listMappings()


    # TAP
    TAP = pd.DataFrame({"offset": range(len(tap_numbers)), 'TAP': tap_numbers})
    assert len(np.intersect1d(TAP.TAP, Tap_ptype.TAP)) == len(Tap_ptype.TAP)
    TAP = TAP.merge(Tap_ptype, how="outer")
    TAP.set_index("TAP", drop=True, inplace=True)

    # TAZ
    # TAZ = pd.DataFrame({'TAZ': taz_numbers})
    # TAZ = TAZ.merge(Zone_term, how="outer")
    # TAZ = TAZ.merge(Zone_park, how="outer")

    TAZ = pd.DataFrame({"offset": range(len(taz_numbers)), "TAZ": taz_numbers})
    assert len(np.intersect1d(TAZ.TAZ, Zone_term.TAZ)) == len(Zone_term.TAZ)
    TAZ = TAZ.merge(Zone_term, how="left")
    assert len(np.intersect1d(TAZ.index, Zone_park.TAZ)) == len(Zone_park.TAZ)
    TAZ = TAZ.merge(Zone_park, how="left")
    TAZ.set_index("TAZ", drop=True, inplace=True)

    # MAZ
    MAZ = mgra13_based_input2012
    MAZ.rename(columns={'mgra': 'MAZ', 'taz': 'TAZ'}, inplace=True)
    MAZ.set_index("MAZ", drop=True, inplace=True)

    # MAZtoMAZ
    bikeMgraLogsum.rename(
        columns={'i': 'OMAZ', 'j': 'DMAZ', 'logsum':'bike_logsum', 'time':'bike_time'},
        inplace=True)
    walkMgraEquivMinutes.rename(
        columns={'i': 'OMAZ', 'j': 'DMAZ', 'percieved':'walk_perceived', 'actual':'walk_actual', 'gain':'walk_gain'},
        inplace=True)
    MAZtoMAZ = pd.merge(bikeMgraLogsum, walkMgraEquivMinutes, on=['OMAZ','DMAZ'])
    print "MAZtoMAZ columns", MAZtoMAZ.columns.values
    print "MAZtoMAZ len", len(MAZtoMAZ.index)

    # MAZtoTAP
    walkMgraTapEquivMinutes.rename(columns={'mgra': 'MAZ', 'tap': 'TAP'}, inplace=True)
    walkMgraTapEquivMinutes['MODE'] = 'WALK'

    print "walkMgraTapEquivMinutes columns", walkMgraTapEquivMinutes.columns.values
    print "walkMgraTapEquivMinutes len", len(walkMgraTapEquivMinutes.index)

    # expand from TAZtoTAP to MAZtoTAP
    tapsPerTaz = Accessam.groupby('TAZ').count()['TAP']
    Accessam.set_index('TAZ', drop=False, inplace=True)
    Accessam = Accessam.loc[MAZ.TAZ]  # explode
    MAZ['TAPS'] = tapsPerTaz.loc[MAZ.TAZ].tolist()
    Accessam['MAZ'] = np.repeat(MAZ.index.tolist(), MAZ.TAPS.tolist())
    Accessam['MODE'] = 'DRIVE'
    MAZtoTAP = pd.concat([walkMgraTapEquivMinutes, Accessam])

    # write tables
    TAP.to_hdf(output_folder + outputDataStoreFileName, "TAP", complib='zlib', complevel=7)
    TAZ.to_hdf(output_folder + outputDataStoreFileName, "TAZ")
    MAZ.to_hdf(output_folder + outputDataStoreFileName, "MAZ")
    MAZtoMAZ.to_hdf(output_folder + outputDataStoreFileName, "MAZtoMAZ")
    MAZtoTAP.to_hdf(output_folder + outputDataStoreFileName, "MAZtoTAP")

    print("created " + output_folder + outputDataStoreFileName)

    ######### TAZ skim

    output_taz_skim_file = 'taz_skims.omx'
    output_taz_skims = openmatrix.open_file(output_folder + output_taz_skim_file, "w")

    taz_skim_manifest = {
        'impdan_AM.omx': {'*SCST_AM': 'SOV_COST__AM', '*STM_AM (Skim)': 'SOV_TIME__AM'},
        'impdat_AM.omx': {'*SCST_AM': 'SOVTOLL_COST__AM', '*STM_AM (Skim)': 'SOVTOLL_TIME__AM'},
    }
    for f, key_map in taz_skim_manifest.iteritems():
        with openmatrix.open_file(folder + f) as input_skims:
            print "%s shape %s mappings" % (f, input_skims.shape()), input_skims.listMappings()

            for m in input_skims.listMappings():
                assert input_skims.mapping(m).keys() == taz_numbers

            # for skimName in input_skims.listMatrices():
            #     print skimName

            for in_key, out_key in key_map.iteritems():
                print "copying %s %s to %s" % (f, in_key, out_key)
                output_taz_skims[out_key] = input_skims[in_key]

    #################################################
    ### FIXME - Fake data for 3d skims
    taz_skim_manifest = {
        'impdan_AM.omx': {'*SCST_AM': 'SOV_COST__PM', '*STM_AM (Skim)': 'SOV_TIME__PM'},
        'impdat_AM.omx': {'*SCST_AM': 'SOVTOLL_COST__PM', '*STM_AM (Skim)': 'SOVTOLL_TIME__PM'},
    }
    for f, key_map in taz_skim_manifest.iteritems():
        with openmatrix.open_file(folder + f) as input_skims:
            for in_key, out_key in key_map.iteritems():
                print "copying %s %s to %s" % (f, in_key, out_key)
                np_array = np.asanyarray(input_skims[in_key])
                output_taz_skims[out_key] = np_array + 1.0
    #################################################


    # read bikeTazLogsum as convert to OMX
    bikeTazLogsum = pd.read_csv(folder + "bikeTazLogsum.csv")
    bikeTazLogsum['index_i'] = TAZ.loc[bikeTazLogsum.i].offset.tolist()
    bikeTazLogsum['index_j'] = TAZ.loc[bikeTazLogsum.j].offset.tolist()

    # bike_logsum
    logsum = np.zeros([len(taz_numbers), len(taz_numbers)])
    logsum[bikeTazLogsum['index_i'], bikeTazLogsum['index_j']] = bikeTazLogsum.logsum

    print "output_taz_skims shape %s skim shape %s" % (output_taz_skims.shape(), logsum.shape)
    output_taz_skims['bike_logsum'] = logsum

    # bike_time
    time = np.zeros([len(taz_numbers), len(taz_numbers)])
    time[bikeTazLogsum['index_i'], bikeTazLogsum['index_j']] = bikeTazLogsum.time
    output_taz_skims['bike_time'] = time

    output_taz_skims.close()

    # print summary of what we built
    print "\n##### Summary of %s" % output_taz_skim_file
    with openmatrix.open_file(output_folder + output_taz_skim_file) as skims:
        print skims
    print "\n#####\n"

    ######### TAP skim

    output_tap_skim_file = 'tap_skims.omx'
    output_tap_skims = openmatrix.open_file(output_folder + output_tap_skim_file, "w")

    tap_skim_files = ['implocl_AM.omx', 'implocl_AMo.omx', 'impprem_AM.omx', 'impprem_AMo.omx',
                      'tranTotalTrips_AM.omx', ]


    tap_skim_manifest = {
        'implocl_AMo.omx': {
            'Fare': 'LOCAL_BUS_FARE__AM',
            'Initial Wait Time': 'LOCAL_BUS_INITIAL_WAIT__AM',
            'Number of Transfers': 'LOCAL_BUS_NUM_TRANSFERS__AM',
            'Total IV Time': 'LOCAL_BUS_IVT__AM',
            'Transfer Wait Time': 'LOCAL_BUS_TRANSFER_WAIT__AM',
            'Walk Time': 'LOCAL_BUS_WALK_TIME__AM'
        },
        'impprem_AMo.omx': {
            'Fare': 'PREM_BUS_FARE__AM',
            'IVT:BRT': 'PREM_BUS_IVT_BRT__AM',
            'IVT:CR': 'PREM_BUS_IVT_CR__AM',
            'IVT:EXP': 'PREM_BUS_IVT_EXP__AM',
            'IVT:LB': 'PREM_BUS_IVT_LB__AM',
            'IVT:LR': 'PREM_BUS_IVT_LR__AM',
            'IVT:Sum': 'PREM_BUS_IVT_SUM__AM',
            'Initial Wait Time': 'PREM_BUS_INITIAL_WAIT__AM',
            'Length:BRT': 'PREM_BUS_LENGTH_BRT__AM',
            'Length:CR': 'PREM_BUS_LENGTH_CR__AM',
            'Length:EXP': 'PREM_BUS_LENGTH_EXP__AM',
            'Length:LB': 'PREM_BUS_LENGTH_LB__AM',
            'Length:LR': 'PREM_BUS_LENGTH_LR__AM',
            'Main Mode': 'PREM_BUS_MAIN_MODE__AM',
            'Number of Transfers': 'PREM_BUS_NUM_TRANSFERS__AM',
            'Transfer Wait Time': 'PREM_BUS_TRANSFER_WAIT__AM',
            'Walk Time': 'PREM_BUS_WALK_TIME__AM'
        }
    }
    for f, key_map in tap_skim_manifest.iteritems():
        with openmatrix.open_file(folder + f) as input_skims:
            print "%s shape %s mappings" % (f, input_skims.shape()), input_skims.listMappings()

            for m in input_skims.listMappings():
                assert input_skims.mapping(m).keys() == tap_numbers

            # for skimName in input_skims.listMatrices():
            #     print skimName

            for in_key, out_key in key_map.iteritems():
                print "copying %s %s to %s" % (f, in_key, out_key)
                output_tap_skims[out_key] = input_skims[in_key]

    #################################################
    ### FIXME - Fake data for 3d skims
    tap_skim_manifest = {
        'implocl_AMo.omx': {
            'Fare': 'LOCAL_BUS_FARE__PM',
            'Initial Wait Time': 'LOCAL_BUS_INITIAL_WAIT__PM',
            'Number of Transfers': 'LOCAL_BUS_NUM_TRANSFERS__PM',
            'Total IV Time': 'LOCAL_BUS_IVT__PM',
            'Transfer Wait Time': 'LOCAL_BUS_TRANSFER_WAIT__PM',
            'Walk Time': 'LOCAL_BUS_WALK_TIME__PM'
        },
        'impprem_AMo.omx': {
            'Fare': 'PREM_BUS_FARE__PM',
            'IVT:BRT': 'PREM_BUS_IVT_BRT__PM',
            'IVT:CR': 'PREM_BUS_IVT_CR__PM',
            'IVT:EXP': 'PREM_BUS_IVT_EXP__PM',
            'IVT:LB': 'PREM_BUS_IVT_LB__PM',
            'IVT:LR': 'PREM_BUS_IVT_LR__PM',
            'IVT:Sum': 'PREM_BUS_IVT_SUM__PM',
            'Initial Wait Time': 'PREM_BUS_INITIAL_WAIT__PM',
            'Length:BRT': 'PREM_BUS_LENGTH_BRT__PM',
            'Length:CR': 'PREM_BUS_LENGTH_CR__PM',
            'Length:EXP': 'PREM_BUS_LENGTH_EXP__PM',
            'Length:LB': 'PREM_BUS_LENGTH_LB__PM',
            'Length:LR': 'PREM_BUS_LENGTH_LR__PM',
            'Main Mode': 'PREM_BUS_MAIN_MODE__PM',
            'Number of Transfers': 'PREM_BUS_NUM_TRANSFERS__PM',
            'Transfer Wait Time': 'PREM_BUS_TRANSFER_WAIT__PM',
            'Walk Time': 'PREM_BUS_WALK_TIME__PM'
        }
    }
    for f, key_map in tap_skim_manifest.iteritems():
        with openmatrix.open_file(folder + f) as input_skims:
            for in_key, out_key in key_map.iteritems():
                print "copying %s %s to %s" % (f, in_key, out_key)
                np_array = np.asanyarray(input_skims[in_key])
                output_tap_skims[out_key] = np_array + 1.0
    #################################################

    output_tap_skims.close()

    # print summary of what we just built
    print "\n##### Summary of %s" % output_tap_skim_file
    with openmatrix.open_file(output_folder + output_tap_skim_file) as skims:
        print skims
    print "\n#####\n"
