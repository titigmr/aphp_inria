from jellyfish import jaro_winkler_similarity
import pandas as pd
import numpy as np


class Duplication:
    """
    Find duplicate values in a Dataframe using the function detect_duplicates.

    Parameters
    ----------
    variable_testing : variables considered to find duplicates
    var_similarity : variables considered to assess the similarity
    var_threshold : variables considered to assess if an observation is a duplicate
    df_pcr : dataframe of pcr test 
    confidence : retained threshold for the similarity between two values
    threshold : pourcentage of identical values considered to assess if an observation is duplicate
    metric : function to compare string (default is Jaro Winkler similarity)
    """
    
    def __init__(self, variable_testing=None, var_threshold=None, df_pcr=None, var_similarity=None, 
                confidence=0.8, threshold=0.7, metric=None, remove_dupli_pi=False):

        self.var_threshold = var_threshold
        self.var_similarity = var_similarity
        self.confidence = confidence
        self.threshold = threshold
        self.variable_testing = variable_testing
        self.df_pcr = df_pcr
        self.remove_dupli_pi = remove_dupli_pi  
        
        if metric is None:
            self.metric = jaro_winkler_similarity
        else :
            self.metric = metric


    def detect_duplicates(self, df_patient):
        """
        For each testing variable find all duplicates in a pandas dataframe and 
        display the number of removed duplicates.

        Return
        ------
        df_patient : dataframe without duplicates 
        """

        df_patient_init = df_patient.copy()

        if self.variable_testing is None:
            self.variable_testing = df_patient.columns
        
        
        # get all unique values for a given testing variable
        for variable in self.variable_testing:
            all_unique = df_patient[variable][df_patient[variable].duplicated(
                False)].unique()

            # get index of duplicates found
            list_dupli = self.__get_indice_duplicated__(
                df_patient, self.df_pcr, variable, all_unique)
            
            # remove duplicate values from an input dataframe 
            df_patient = self.__df_deduplicate__(df_patient, list_dupli, variable)

        # remove duplicates id
        if self.remove_dupli_pi:
            if 'patient_id' in df_patient.columns:
                index_dupli_pi = df_patient[df_patient.patient_id.duplicated(False)].index
                df_patient = self.__df_deduplicate__(df_patient, index_dupli_pi, 'patient_id')
            else : 
                print('No patient id column')

        # attribute that shows the number of data removed
        self.removed = round(
            1 - (df_patient.shape[0] / df_patient_init.shape[0]), 2)

        return df_patient

    def __get_indice_duplicated__(self, df_patient, df_pcr, variable, all_dupli):
        """
        Find index of duplicate values.

        Parameters
        ----------
        df_patient : dataframe, dataset patient
        df_pcr : dataframe, dataset pcr
        variable : str, reference variable to retain duplicates
        all_dupli : list, all uniques values 
        """
        indice_duplicates = []

        for dupli in all_dupli:

            # create a cluster of duplicates observations according to 
            # the test variable and return the index of the reference 
            # observation used for the comparison
            clus, ref = self.__make_cluster__(
                variable, df_patient, df_pcr, dupli)

            # compute for each observation of the cluster the pourcentage of matching 
            # with the reference observation
            
            if self.var_similarity is None:
                self.var_similarity = df_patient.columns

            match = self.__matching_cluster__(clus, ref, self.var_similarity)

            # set a threshold to qualify an observation as duplicate and 
            # retain those that do not exceed this threshold
            
            if self.var_threshold is None:
                self.var_threshold = df_patient.columns

            cm = self.__calculate_matching__(match, self.var_threshold)
            duplicate = cm >= self.threshold
            
            if any(duplicate):
                indice_duplicates.extend(duplicate.index[duplicate])

        return indice_duplicates

    def __make_cluster__(self, variable, df_patient, df_pcr, dupli):
        """
        Create a duplicate observation cluster according to a test variable.

        Parameters 
        ----------
        df_patient : dataframe, dataset patient
        df_pcr : dataframe, dataset pcr
        variable : str, reference variable to retain duplicates
        dupli : str or float, one unique value from the list_dupli

        Return 
        ------
        cluster : dataframe of duplicates
        ref_index : int, index of the reference observation
        """

        cluster = df_patient[df_patient[variable] == dupli]

        # Find all observations of the cluster that have been tested in the table pcr
        if df_pcr is None : 
            ref_index = cluster.index[0]
            return cluster, ref_index
        
        is_tested = cluster.patient_id.isin(df_pcr.patient_id)
        
        # - if one observation is tested : use it as a baseline observation, else
        # choose the first observation
        # - if two or more observations are tested : find out if one of the
        # patient is postive. Retain the index of the first positive patient, 
        # if there is one. Else, retains the first observation index.
        
        if any(is_tested):
            index_tested = is_tested.index[is_tested]
            h_many_id = len(index_tested)

            if h_many_id == 1:
                ref_index = index_tested[0]
            else:
                is_positive = self.__find_positive__(index_tested, df_pcr, df_patient)
                if any(is_positive):
                    index_positive = self.__get_positive__(df_patient, df_pcr, is_positive)
                    ref_index = index_positive[np.isin(index_positive, index_tested)][0]
                else:
                    ref_index = index_tested[0]
        else:
            ref_index = is_tested.index[0]

        return cluster, ref_index

    def __matching_cluster__(self, cluster, ref_index, var_similarity):
        """
        Compute for each observation of the cluster the matching pourcentage 
        with the reference observation.

        Parameters
        ----------
        cluster : dataframe of duplicates
        ref_index : int, index of the reference observation
        var_similarity : float, threshold to qualify an observation as duplicate

        Return
        ------
        dataframe : return a boolean dataframe
        """
        matching = list()

        for line in cluster.index:
            if not(line == ref_index):

                var_identical = {}
                
                # For each column of each row (excluding the reference 
                # index) compute the similarity between two strings (with an 
                # algorithm) for the chosen variables. 
                # Else, only compare these values.

                for var in cluster.columns:
                    var_identical["index"] = line

                    if var in var_similarity:

                        var_identical[var] = self.metric(cluster.loc[line, var],
                                                    cluster.loc[ref_index, var]) > self.confidence

                    else:
                        var_identical[var] = cluster.loc[line, var] == cluster.loc[
                        ref_index, var]

                matching.append(var_identical)

        dataframe = pd.DataFrame(matching).set_index('index')
        dataframe.index.name = None
        return dataframe

    def __calculate_matching__(self, match, var_threshold):
        """
        Calcule the pourcentage of matching for each observation in cluster 
        with chosen variables.
        """
        return match[var_threshold].sum(axis=1) / len(var_threshold)

    def __df_deduplicate__(self, df_patient, indice_duplicates, variable):
        """
        Remove duplicates from a pandas dataframe with the indices duplicated.
        """
        list_d = np.array(indice_duplicates)
        print(f"{variable} : {len(indice_duplicates)} lines removed")
        return df_patient.loc[np.setdiff1d(df_patient.index, list_d)]

    def __find_positive__(self, index_tested, df_pcr, df_patient):
        """
        Find if a patient is positive from a pcr dataframe.
        """
        is_positive = df_pcr[df_pcr.patient_id.isin(
            df_patient.loc[index_tested].patient_id)].pcr == "P"
        return is_positive

    def __get_positive__(self, df_patient, df_pcr, is_positive):
        """
        Retains the line of positive patient.
        """
        return df_patient[
        df_patient.patient_id.isin(
            df_pcr.patient_id[is_positive.index[is_positive]])].index


def prepare_patient(df_patient):
    """
    Prepare dataframe patient. This function create :
    localisation, full_address, full_name and born_age.
    """

    df_patient = df_patient.fillna('')
    
    # born and age
    df_patient["born_age"] = df_patient.apply(lambda x: str(
    	x["date_of_birth"]).replace('.0', '').replace('nan','') + " " + str(
    	x["age"]).replace('.0','').replace('nan',''), axis=1)
    
    # localisation (postcode, suburb and state)
    df_patient.street_number = df_patient.street_number.replace(
        {"": 0}).astype(int).astype(str).replace({"0": ""})
    df_patient["localisation"] = df_patient.apply(lambda x : x["postcode"] + " " + 
    	x["state"] + " " + x["suburb"], axis=1)
    
    # full address (number and adress)
    df_patient["full_address"] = df_patient.apply(lambda x : x["street_number"] + " " 
                                                  + x["address_1"], axis=1)
    # full name (surname and given name)
    df_patient["full_name"] = df_patient["surname"] + " " + df_patient["given_name"]
    
    return df_patient


def prepare_pcr(df_pcr, positive_pi, not_dupli_pcr):
    """
    Deduplicate pcr table
    """
    keep = pd.concat([positive_pi, not_dupli_pcr])
    df_pcr = df_pcr.drop_duplicates(keep=False, subset=["patient_id"])
    df_pcr = pd.concat([df_pcr, keep])
    return df_pcr
